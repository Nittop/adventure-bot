import discord
from discord.ext import commands
from discord import app_commands
import random
import json
import os
import tempfile
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

intents = discord.Intents.default()
bot = commands.Bot(command_prefix="!", intents=intents)

DATA_FILE = "discord-bot/rpg_data.json"

# ═══════════════════════════════════════════════════════════════════════════════
#  GAME CONSTANTS
# ═══════════════════════════════════════════════════════════════════════════════

LEVEL_TITLES = [
    (1,   "🌱 Novice"),
    (5,   "🎣 Apprentice"),
    (10,  "⚓ Journeyman"),
    (20,  "🏆 Expert"),
    (35,  "💎 Master"),
    (50,  "🔱 Grandmaster"),
    (75,  "🌊 Ocean Legend"),
    (100, "🌌 Mythical Fisher"),
]

def get_title(level: int) -> str:
    title = LEVEL_TITLES[0][1]
    for min_lvl, t in LEVEL_TITLES:
        if level >= min_lvl:
            title = t
    return title

def xp_needed(level: int) -> int:
    """XP required to reach the next level (harder curve)."""
    return int(level ** 1.6 * 400)

# ─── RODS (9 total) ───────────────────────────────────────────────────────────
# luck       = bonus rare-fish weight (additive, e.g. 0.10 = +10%)
# dup        = chance to catch a second fish on the same cast
# mut        = extra mutation chance added on top of base roll
# special    = unique special ability key (None = no special)
RODS = {
    "Wooden": {
        "emoji": "🪵", "price": 0, "power": 1.0, "tier": 1,
        "luck": 0.00, "dup": 0.00, "mut": 0.00, "special": None,
        "desc": "A plain starter rod. No buffs whatsoever.",
    },
    "Bamboo": {
        "emoji": "🎋", "price": 350, "power": 1.5, "tier": 2,
        "luck": 0.04, "dup": 0.00, "mut": 0.00, "special": None,
        "desc": "Flexible bamboo. Slightly luckier casts (+4% luck).",
    },
    "Steel": {
        "emoji": "🔩", "price": 900, "power": 2.2, "tier": 3,
        "luck": 0.04, "dup": 0.04, "mut": 0.00, "special": None,
        "desc": "Heavy-duty steel. Sometimes snags two fish (+4% dup).",
    },
    "Carbon": {
        "emoji": "🖤", "price": 2500, "power": 3.2, "tier": 4,
        "luck": 0.07, "dup": 0.05, "mut": 0.03, "special": None,
        "desc": "Ultra-light carbon fiber. Starts attracting mutations (+3% mut).",
    },
    "Pro": {
        "emoji": "⭐", "price": 5500, "power": 4.5, "tier": 5,
        "luck": 0.10, "dup": 0.07, "mut": 0.05, "special": None,
        "desc": "Tournament-grade. Solid all-around buffs (+10% luck, +7% dup, +5% mut).",
    },
    "Master": {
        "emoji": "🏆", "price": 14000, "power": 6.0, "tier": 6,
        "luck": 0.13, "dup": 0.09, "mut": 0.08, "special": "echo",
        "desc": "⚡ ECHO — 6% chance a phantom cast brings a free bonus fish alongside your catch.",
    },
    "Crystal": {
        "emoji": "💎", "price": 35000, "power": 8.0, "tier": 7,
        "luck": 0.16, "dup": 0.11, "mut": 0.12, "special": "resonance",
        "desc": "✨ RESONANCE — guaranteed chest every 10 casts, no luck roll needed.",
    },
    "Dragon": {
        "emoji": "🐉", "price": 90000, "power": 11.0, "tier": 8,
        "luck": 0.20, "dup": 0.14, "mut": 0.17, "special": "inferno",
        "desc": "🔥 INFERNO — volcanic fire fish can appear in ANY biome you fish in.",
    },
    "Void": {
        "emoji": "🌌", "price": 250000, "power": 16.0, "tier": 9,
        "luck": 0.25, "dup": 0.18, "mut": 0.23, "special": "void_tear",
        "desc": "🌌 VOID TEAR — 8% chance to rip a fish from the next biome tier above yours.",
    },
}

# ─── BAITS (5 total) ──────────────────────────────────────────────────────────
BAITS = {
    "Basic":   {"emoji": "🪱", "price": 0,      "power": 1.0,  "desc": "A humble earthworm."},
    "Worm":    {"emoji": "🦟", "price": 250,    "power": 1.5,  "desc": "Juicy nightcrawler worm."},
    "Lucky":   {"emoji": "🍀", "price": 1200,   "power": 2.2,  "desc": "Said to attract rare fish."},
    "Magic":   {"emoji": "✨", "price": 6000,   "power": 3.5,  "desc": "Enchanted by an ancient angler."},
    "Golden":  {"emoji": "🌟", "price": 25000,  "power": 6.0,  "desc": "Pure liquid gold. Legends-only bait."},
}

# ─── BOATS (7 total) ──────────────────────────────────────────────────────────
BOATS = {
    "Rowboat":         {"emoji": "🚣",  "price": 0,       "power": 1.0,  "tier": 1, "desc": "A humble start on the water."},
    "Canoe":           {"emoji": "🛶",  "price": 600,     "power": 1.3,  "tier": 2, "desc": "Silent and maneuverable."},
    "Sailboat":        {"emoji": "⛵",  "price": 2500,    "power": 1.8,  "tier": 3, "desc": "Wind-powered ocean access."},
    "Motorboat":       {"emoji": "🚤",  "price": 8000,    "power": 2.8,  "tier": 4, "desc": "Fast and dependable."},
    "Speedboat":       {"emoji": "💨",  "price": 20000,   "power": 4.0,  "tier": 5, "desc": "Blazing across the waves."},
    "Yacht":           {"emoji": "🛥️", "price": 55000,   "power": 5.5,  "tier": 6, "desc": "Luxury vessel for serious fishers."},
    "Deep Sea Vessel": {"emoji": "🚢",  "price": 140000,  "power": 9.0,  "tier": 7, "desc": "Built for the abyssal depths."},
}

# ─── BIOMES ───────────────────────────────────────────────────────────────────
BIOMES = {
    "river":    {"name": "🏞️ River",          "min_level": 1,  "min_boat_tier": 1, "desc": "Calm freshwater. Good for beginners."},
    "lake":     {"name": "🏔️ Mountain Lake",  "min_level": 8,  "min_boat_tier": 2, "desc": "Crystal-clear alpine waters."},
    "ocean":    {"name": "🌊 Ocean",           "min_level": 20, "min_boat_tier": 3, "desc": "Vast, reward-rich saltwater."},
    "volcanic": {"name": "🌋 Volcanic Waters", "min_level": 38, "min_boat_tier": 5, "desc": "Boiling waters home to fire fish."},
    "arctic":   {"name": "❄️ Arctic Sea",      "min_level": 58, "min_boat_tier": 6, "desc": "Frozen waters with legendary catches."},
    "abyss":    {"name": "🌑 Abyssal Depths",  "min_level": 80, "min_boat_tier": 7, "desc": "The deepest unknown. Mythical fish lurk here."},
}

# ─── FISH ─────────────────────────────────────────────────────────────────────
# weight = relative catch frequency; higher = more common
# value = (min_coins, max_coins) per fish sold
# rod_tier = minimum rod tier needed to catch this fish
FISH_DATA = {
    # ── River ────────────────────────────────────────────────
    "Minnow":           {"emoji": "🐟", "biomes": ["river"],            "weight": 55, "value": (5,  30),    "xp": 8,   "rod_tier": 1},
    "Perch":            {"emoji": "🐠", "biomes": ["river"],            "weight": 42, "value": (15, 60),    "xp": 13,  "rod_tier": 1},
    "Bass":             {"emoji": "🎣", "biomes": ["river", "lake"],    "weight": 30, "value": (30, 100),   "xp": 20,  "rod_tier": 1},
    "Catfish":          {"emoji": "🐡", "biomes": ["river"],            "weight": 22, "value": (45, 130),   "xp": 28,  "rod_tier": 2},
    "River Trout":      {"emoji": "🫐", "biomes": ["river", "lake"],    "weight": 16, "value": (70, 180),   "xp": 38,  "rod_tier": 2},
    # ── Lake ─────────────────────────────────────────────────
    "Lake Carp":        {"emoji": "🦞", "biomes": ["lake"],             "weight": 38, "value": (55, 145),   "xp": 30,  "rod_tier": 2},
    "Pike":             {"emoji": "🗡️","biomes": ["lake"],             "weight": 24, "value": (90, 240),   "xp": 42,  "rod_tier": 3},
    "Rainbow Trout":    {"emoji": "🌈", "biomes": ["lake"],             "weight": 18, "value": (120, 320),  "xp": 55,  "rod_tier": 3},
    "Freshwater Eel":   {"emoji": "🐍", "biomes": ["lake", "ocean"],   "weight": 12, "value": (170, 420),  "xp": 68,  "rod_tier": 3},
    "Giant Perch":      {"emoji": "🐊", "biomes": ["lake"],             "weight": 8,  "value": (250, 600),  "xp": 85,  "rod_tier": 4},
    # ── Ocean ────────────────────────────────────────────────
    "Mackerel":         {"emoji": "🐟", "biomes": ["ocean"],            "weight": 32, "value": (110, 280),  "xp": 45,  "rod_tier": 3},
    "Tuna":             {"emoji": "🐡", "biomes": ["ocean"],            "weight": 22, "value": (230, 580),  "xp": 72,  "rod_tier": 4},
    "Swordfish":        {"emoji": "⚔️", "biomes": ["ocean"],            "weight": 14, "value": (380, 900),  "xp": 95,  "rod_tier": 4},
    "Shark":            {"emoji": "🦈", "biomes": ["ocean"],            "weight": 8,  "value": (650, 1600), "xp": 130, "rod_tier": 5},
    "Manta Ray":        {"emoji": "🦅", "biomes": ["ocean"],            "weight": 5,  "value": (900, 2200), "xp": 165, "rod_tier": 5},
    "Octopus":          {"emoji": "🐙", "biomes": ["ocean", "abyss"],  "weight": 10, "value": (450, 1100), "xp": 105, "rod_tier": 4},
    # ── Volcanic ─────────────────────────────────────────────
    "Fire Carp":        {"emoji": "🔴", "biomes": ["volcanic"],         "weight": 22, "value": (700, 1800),  "xp": 130, "rod_tier": 5},
    "Lava Eel":         {"emoji": "🔥", "biomes": ["volcanic"],         "weight": 16, "value": (1000, 2600), "xp": 170, "rod_tier": 5},
    "Magma Bass":       {"emoji": "💎", "biomes": ["volcanic"],         "weight": 10, "value": (1600, 4000), "xp": 220, "rod_tier": 6},
    "Thunder Ray":      {"emoji": "⚡", "biomes": ["volcanic"],         "weight": 6,  "value": (2500, 6000), "xp": 290, "rod_tier": 6},
    "Volcanic Tuna":    {"emoji": "🌋", "biomes": ["volcanic"],         "weight": 3,  "value": (4500, 11000),"xp": 380, "rod_tier": 7},
    # ── Arctic ───────────────────────────────────────────────
    "Ice Salmon":       {"emoji": "❄️", "biomes": ["arctic"],           "weight": 20, "value": (1200, 3000), "xp": 220, "rod_tier": 6},
    "Frost Carp":       {"emoji": "🧊", "biomes": ["arctic"],           "weight": 13, "value": (2000, 5000), "xp": 290, "rod_tier": 6},
    "Arctic Char":      {"emoji": "🔵", "biomes": ["arctic"],           "weight": 8,  "value": (3500, 8500), "xp": 370, "rod_tier": 7},
    "Polar Tuna":       {"emoji": "🐋", "biomes": ["arctic"],           "weight": 4,  "value": (6000, 14000),"xp": 480, "rod_tier": 7},
    "Glacial Pike":     {"emoji": "☃️", "biomes": ["arctic"],           "weight": 2,  "value": (10000,25000),"xp": 620, "rod_tier": 8},
    # ── Abyss ────────────────────────────────────────────────
    "Abyssal Kraken":   {"emoji": "👾", "biomes": ["abyss"],            "weight": 12, "value": (5000, 12000), "xp": 550, "rod_tier": 7},
    "Void Serpent":     {"emoji": "🌌", "biomes": ["abyss"],            "weight": 7,  "value": (10000,25000), "xp": 720, "rod_tier": 8},
    "Deep Horror":      {"emoji": "💀", "biomes": ["abyss"],            "weight": 4,  "value": (20000,50000), "xp": 950, "rod_tier": 8},
    "Crystal Manta":    {"emoji": "🔮", "biomes": ["abyss"],            "weight": 2,  "value": (40000,100000),"xp": 1300,"rod_tier": 9},
    "Shadow Whale":     {"emoji": "🌑", "biomes": ["abyss"],            "weight": 1,  "value": (80000,200000),"xp": 2000,"rod_tier": 9},
}

# ─── CHESTS ───────────────────────────────────────────────────────────────────
CHESTS = {
    "Common":    {"emoji": "📦", "color": 0x95A5A6, "min_coins": 80,    "max_coins": 400,    "chance": 0.10},
    "Uncommon":  {"emoji": "💚", "color": 0x2ECC71, "min_coins": 400,   "max_coins": 2000,   "chance": 0.045},
    "Rare":      {"emoji": "💙", "color": 0x3498DB, "min_coins": 2000,  "max_coins": 8000,   "chance": 0.018},
    "Epic":      {"emoji": "💜", "color": 0x9B59B6, "min_coins": 8000,  "max_coins": 30000,  "chance": 0.006},
    "Legendary": {"emoji": "🌟", "color": 0xFFD700, "min_coins": 30000, "max_coins": 100000, "chance": 0.0015},
}

# ─── MUTATIONS ────────────────────────────────────────────────────────────────
# base_chance = base roll before rod/power bonuses are applied
# value_mult  = coin multiplier
# xp_mult     = XP multiplier
# bonus       = extra chest rarity granted on top (None | "Common" | "Uncommon" | "Rare" | "Epic" | "Legendary")
MUTATIONS = {
    "Golden":      {"emoji": "⭐", "base_chance": 0.080, "value_mult": 3.0,  "xp_mult": 1.0, "bonus": None,        "desc": "3× coins"},
    "Giant":       {"emoji": "🔵", "base_chance": 0.070, "value_mult": 2.0,  "xp_mult": 2.0, "bonus": None,        "desc": "2× coins & XP"},
    "Tidal":       {"emoji": "🌊", "base_chance": 0.060, "value_mult": 2.5,  "xp_mult": 1.5, "bonus": None,        "desc": "2.5× coins, 1.5× XP"},
    "Corrupted":   {"emoji": "👾", "base_chance": 0.055, "value_mult": 1.5,  "xp_mult": 3.0, "bonus": None,        "desc": "1.5× coins, 3× XP"},
    "Spectral":    {"emoji": "👻", "base_chance": 0.045, "value_mult": 1.0,  "xp_mult": 3.0, "bonus": "Common",    "desc": "3× XP + Common Chest"},
    "Radioactive": {"emoji": "☢️", "base_chance": 0.040, "value_mult": 4.0,  "xp_mult": 1.5, "bonus": None,        "desc": "4× coins, 1.5× XP"},
    "Albino":      {"emoji": "🤍", "base_chance": 0.035, "value_mult": 4.0,  "xp_mult": 1.0, "bonus": None,        "desc": "Rare white variant — 4× coins"},
    "Blazing":     {"emoji": "🔥", "base_chance": 0.030, "value_mult": 3.0,  "xp_mult": 1.0, "bonus": "Uncommon",  "desc": "3× coins + Uncommon Chest"},
    "Shadow":      {"emoji": "🌑", "base_chance": 0.025, "value_mult": 5.0,  "xp_mult": 0.5, "bonus": None,        "desc": "5× coins, half XP"},
    "Rainbow":     {"emoji": "🌈", "base_chance": 0.018, "value_mult": 5.0,  "xp_mult": 2.0, "bonus": "Rare",      "desc": "5× coins, 2× XP + Rare Chest"},
    "Crystal":     {"emoji": "💎", "base_chance": 0.012, "value_mult": 6.0,  "xp_mult": 2.0, "bonus": None,        "desc": "Crystal form — 6× coins"},
    "Ancient":     {"emoji": "🦴", "base_chance": 0.006, "value_mult": 8.0,  "xp_mult": 3.0, "bonus": "Epic",      "desc": "Prehistoric — 8× coins, 3× XP + Epic Chest"},
    "Void":        {"emoji": "🌌", "base_chance": 0.002, "value_mult": 15.0, "xp_mult": 5.0, "bonus": "Legendary", "desc": "VOID — 15× coins, 5× XP + Legendary Chest"},
}

# ─── POWERS (buyable passives) ────────────────────────────────────────────────
# Each power can be owned once. Bonuses stack with rods.
# luck / dup / mut / xp_bonus / coin_bonus / chest_bonus are all additive floats
POWERS = {
    "Lucky Charm":    {"emoji": "🍀", "price": 3000,  "luck": 0.08, "dup": 0.00, "mut": 0.00, "xp_bonus": 0.00, "coin_bonus": 0.00, "chest_bonus": 0.00, "desc": "+8% rare fish luck"},
    "XP Tome":        {"emoji": "📚", "price": 5000,  "luck": 0.00, "dup": 0.00, "mut": 0.00, "xp_bonus": 0.15, "coin_bonus": 0.00, "chest_bonus": 0.00, "desc": "+15% XP from every catch"},
    "Fish Magnet":    {"emoji": "🧲", "price": 6000,  "luck": 0.00, "dup": 0.08, "mut": 0.00, "xp_bonus": 0.00, "coin_bonus": 0.00, "chest_bonus": 0.00, "desc": "+8% chance to catch a duplicate fish"},
    "Mutation Serum": {"emoji": "🧪", "price": 8000,  "luck": 0.00, "dup": 0.00, "mut": 0.08, "xp_bonus": 0.00, "coin_bonus": 0.00, "chest_bonus": 0.00, "desc": "+8% mutation chance per cast"},
    "Treasure Sense": {"emoji": "🔮", "price": 10000, "luck": 0.00, "dup": 0.00, "mut": 0.00, "xp_bonus": 0.00, "coin_bonus": 0.00, "chest_bonus": 0.25, "desc": "+25% chest find rate"},
    "Double Daily":   {"emoji": "📅", "price": 12000, "luck": 0.00, "dup": 0.00, "mut": 0.00, "xp_bonus": 0.00, "coin_bonus": 0.00, "chest_bonus": 0.00, "desc": "Doubles your /daily reward permanently"},
    "Golden Net":     {"emoji": "🪤", "price": 15000, "luck": 0.00, "dup": 0.00, "mut": 0.00, "xp_bonus": 0.00, "coin_bonus": 0.20, "chest_bonus": 0.00, "desc": "+20% coins from all fish sales"},
    "Ancient Relic":  {"emoji": "🏺", "price": 20000, "luck": 0.05, "dup": 0.05, "mut": 0.12, "xp_bonus": 0.10, "coin_bonus": 0.00, "chest_bonus": 0.10, "desc": "+12% mut, +5% luck & dup, +10% XP & chests"},
    "Void Compass":   {"emoji": "🧭", "price": 30000, "luck": 0.10, "dup": 0.10, "mut": 0.10, "xp_bonus": 0.10, "coin_bonus": 0.10, "chest_bonus": 0.10, "desc": "All bonuses +10% — the ultimate passive item"},
}

# ═══════════════════════════════════════════════════════════════════════════════
#  PERSISTENCE
# ═══════════════════════════════════════════════════════════════════════════════

def load_data() -> dict:
    if not os.path.exists(DATA_FILE):
        return {}
    try:
        with open(DATA_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        logger.error(f"Failed to load data: {e}")
        backup = DATA_FILE + ".corrupt"
        try:
            os.replace(DATA_FILE, backup)
        except OSError:
            pass
        return {}

players = load_data()

def save_data():
    dir_name = os.path.dirname(DATA_FILE)
    try:
        with tempfile.NamedTemporaryFile(mode="w", dir=dir_name, delete=False, suffix=".tmp") as tmp:
            json.dump(players, tmp)
            tmp.flush()
            os.fsync(tmp.fileno())
            tmp_path = tmp.name
        os.replace(tmp_path, DATA_FILE)
    except OSError as e:
        logger.error(f"Failed to save data: {e}")

PLAYER_DEFAULTS = {
    "coins": 200,
    "xp": 0,
    "level": 1,
    "rod": "Wooden",
    "bait": "Basic",
    "boat": "Rowboat",
    "biome": "river",
    "fish_count": 0,
    "last_daily": None,
    "chests": {},          # chest_rarity → count
    "fish_inventory": {},  # fish_name → count
    "powers": [],          # list of owned power names
    "cast_count": 0,       # total casts (used for Crystal resonance special)
    "play_channel_id": None,  # private play channel ID
}

def _clone_default(v):
    """Deep-copy any mutable default (dict or list) so players never share references."""
    if isinstance(v, dict):
        return v.copy()
    if isinstance(v, list):
        return list(v)
    return v

def get_player(uid) -> dict:
    uid = str(uid)
    if uid not in players:
        players[uid] = {k: _clone_default(v) for k, v in PLAYER_DEFAULTS.items()}
    p = players[uid]
    for key, default in PLAYER_DEFAULTS.items():
        if key not in p:
            p[key] = _clone_default(default)
    return p

# ═══════════════════════════════════════════════════════════════════════════════
#  GAME LOGIC
# ═══════════════════════════════════════════════════════════════════════════════

def player_power(p: dict) -> float:
    rod   = RODS.get(p["rod"],  RODS["Wooden"])
    bait  = BAITS.get(p["bait"], BAITS["Basic"])
    boat  = BOATS.get(p["boat"], BOATS["Rowboat"])
    return rod["power"] * bait["power"] * boat["power"]

def get_player_buffs(p: dict) -> dict:
    """Aggregate all luck/dup/mut/bonus stats from rod + owned powers."""
    rod = RODS.get(p["rod"], RODS["Wooden"])
    buffs = {
        "luck":         rod["luck"],
        "dup":          rod["dup"],
        "mut":          rod["mut"],
        "xp_bonus":     0.0,
        "coin_bonus":   0.0,
        "chest_bonus":  0.0,
        "special":      rod["special"],
        "double_daily": False,
    }
    for pname in p.get("powers", []):
        pw = POWERS.get(pname)
        if not pw:
            continue
        buffs["luck"]        += pw["luck"]
        buffs["dup"]         += pw["dup"]
        buffs["mut"]         += pw["mut"]
        buffs["xp_bonus"]    += pw["xp_bonus"]
        buffs["coin_bonus"]  += pw["coin_bonus"]
        buffs["chest_bonus"] += pw["chest_bonus"]
        if pname == "Double Daily":
            buffs["double_daily"] = True
    return buffs

def roll_mutation(mut_chance: float) -> tuple[str, dict] | tuple[None, None]:
    """Single weighted draw so all mutation rarities stay proportional.

    mut_chance scales every mutation's weight up equally — rarer mutations
    remain proportionally rare even at high mut stacks.
    """
    weights = {name: data["base_chance"] * (1 + mut_chance * 5) for name, data in MUTATIONS.items()}
    total_weight = sum(weights.values())
    # Overall mutation probability capped at 65 %
    overall = min(total_weight, 0.65)
    if random.random() > overall:
        return None, None
    # Pick which mutation by relative weight
    r = random.uniform(0, total_weight)
    cumulative = 0.0
    for name, w in weights.items():
        cumulative += w
        if r <= cumulative:
            return name, MUTATIONS[name]
    return None, None

def check_level_up(p: dict) -> list[int]:
    """Returns list of new levels reached (can be multiple)."""
    new_levels = []
    while p["xp"] >= xp_needed(p["level"]):
        p["xp"] -= xp_needed(p["level"])
        p["level"] += 1
        bonus = p["level"] * 150
        p["coins"] += bonus
        new_levels.append(p["level"])
    return new_levels

def pick_fish(p: dict) -> tuple[str, dict] | tuple[None, None]:
    """Weighted random fish selection for the player's biome and rod tier."""
    biome = p.get("biome", "river")
    rod_tier = RODS.get(p["rod"], RODS["Wooden"])["tier"]
    power = player_power(p)

    # Power boosts weight of higher rod-tier fish
    pool = []
    for name, data in FISH_DATA.items():
        if biome not in data["biomes"]:
            continue
        if data["rod_tier"] > rod_tier:
            continue
        # Scale weight: harder fish get a bigger boost from power
        tier_bonus = 1 + (data["rod_tier"] - 1) * 0.15 * power
        adjusted_weight = max(1, data["weight"] * tier_bonus / data["rod_tier"])
        pool.append((name, data, adjusted_weight))

    if not pool:
        return None, None

    total = sum(w for _, _, w in pool)
    r = random.uniform(0, total)
    cumulative = 0
    for name, data, w in pool:
        cumulative += w
        if r <= cumulative:
            return name, data
    return pool[-1][0], pool[-1][1]

def roll_chest(p: dict, chest_bonus: float = 0.0) -> str | None:
    """Roll for a chest find. Returns chest rarity string or None."""
    power = player_power(p)
    luck_factor = (1 + (power - 1) * 0.05) * (1 + chest_bonus)
    for rarity, data in reversed(list(CHESTS.items())):
        if random.random() < data["chance"] * luck_factor:
            return rarity
    return None

def _add_chest(p: dict, rarity: str):
    p["chests"][rarity] = p["chests"].get(rarity, 0) + 1

def _pick_fish_from_biome(biome: str, rod_tier: int, power: float, luck: float = 0.0):
    """Pick a weighted random fish from a specific biome.

    luck boosts weights of higher rod-tier (rarer) fish so luck stat
    actually shifts the catch distribution toward rarer species.
    """
    pool = []
    for name, data in FISH_DATA.items():
        if biome not in data["biomes"]:
            continue
        if data["rod_tier"] > rod_tier:
            continue
        tier_bonus = 1 + (data["rod_tier"] - 1) * (0.15 * power + luck * 3.0)
        adjusted_weight = max(1, data["weight"] * tier_bonus / data["rod_tier"])
        pool.append((name, data, adjusted_weight))
    if not pool:
        return None, None
    total = sum(w for _, _, w in pool)
    r = random.uniform(0, total)
    cumulative = 0
    for name, data, w in pool:
        cumulative += w
        if r <= cumulative:
            return name, data
    return pool[-1][0], pool[-1][1]

def do_fish(p: dict) -> tuple[discord.Embed, list[int]]:
    """Execute one fishing attempt. Returns (embed, new_levels_list)."""
    buffs   = get_player_buffs(p)
    power   = player_power(p)
    biome   = p.get("biome", "river")
    rod_tier = RODS.get(p["rod"], RODS["Wooden"])["tier"]
    special  = buffs["special"]

    p["cast_count"] = p.get("cast_count", 0) + 1

    # ── void_tear: 8% chance to fish from next biome tier ──
    fish_biome = biome
    biome_keys = list(BIOMES.keys())
    biome_idx  = biome_keys.index(biome) if biome in biome_keys else 0
    if special == "void_tear" and random.random() < 0.08 and biome_idx < len(biome_keys) - 1:
        fish_biome = biome_keys[biome_idx + 1]

    luck = buffs["luck"]
    fish_name, fish = _pick_fish_from_biome(fish_biome, rod_tier, power, luck)

    # ── inferno: volcanic fish can appear anywhere ──
    bonus_fire_name, bonus_fire = None, None
    if special == "inferno" and biome != "volcanic":
        vname, vfish = _pick_fish_from_biome("volcanic", rod_tier, power, luck)
        if vname and random.random() < 0.18:
            bonus_fire_name, bonus_fire = vname, vfish

    if fish_name is None:
        embed = discord.Embed(
            title="❌ Nothing bites...",
            description="Your gear isn't strong enough for this biome. Upgrade your rod or change biome.",
            color=0xE74C3C,
        )
        return embed, []

    # ── base value ──
    base_min, base_max = fish["value"]
    value_scale = (1 + (power - 1) * 0.03) * (1 + buffs["coin_bonus"])
    value = int(random.randint(base_min, base_max) * value_scale)

    # ── mutation roll ──
    mut_name, mut = roll_mutation(buffs["mut"])
    if mut_name:
        # Mutated fish are immediately cashed out at the mutated price so the
        # multiplier isn't lost when sell_all_fish re-rolls base values.
        mut_value = int(value * mut["value_mult"])
        p["coins"] += mut_value
        xp_gained  = int(fish["xp"] * (1 + (power - 1) * 0.04) * mut["xp_mult"] * (1 + buffs["xp_bonus"]))
        if mut["bonus"]:
            _add_chest(p, mut["bonus"])
        # Still count catch and show in embed; don't double-stock inventory
        p["fish_count"] += 1
        p["xp"] += xp_gained
    else:
        mut_value = 0
        xp_gained = int(fish["xp"] * (1 + (power - 1) * 0.04) * (1 + buffs["xp_bonus"]))
        # Store normal fish in inventory to sell later
        p["fish_inventory"][fish_name] = p["fish_inventory"].get(fish_name, 0) + 1
        p["fish_count"] += 1
        p["xp"] += xp_gained

    # ── duplicate roll (non-mutated fish only) ──
    dup_fish_name = None
    if not mut_name and random.random() < buffs["dup"]:
        dup_fish_name = fish_name
        p["fish_inventory"][dup_fish_name] = p["fish_inventory"].get(dup_fish_name, 0) + 1
        p["fish_count"] += 1

    # ── echo special (Master): 6% phantom cast ──
    echo_fish_name = None
    if special == "echo" and random.random() < 0.06:
        ename, efish = _pick_fish_from_biome(biome, rod_tier, power, luck)
        if ename:
            echo_fish_name = ename
            p["fish_inventory"][ename] = p["fish_inventory"].get(ename, 0) + 1
            p["fish_count"] += 1

    # ── inferno bonus fire fish ──
    if bonus_fire_name:
        p["fish_inventory"][bonus_fire_name] = p["fish_inventory"].get(bonus_fire_name, 0) + 1
        p["fish_count"] += 1

    # ── chest rolls ──
    chests_found = []

    # Crystal resonance: guaranteed chest every 10 casts
    if special == "resonance" and p["cast_count"] % 10 == 0:
        chests_found.append("Uncommon")
        _add_chest(p, "Uncommon")

    normal_chest = roll_chest(p, buffs["chest_bonus"])
    if normal_chest:
        chests_found.append(normal_chest)
        _add_chest(p, normal_chest)

    # ── level up ──
    new_levels = check_level_up(p)

    # ── build embed ──
    biome_name = BIOMES.get(biome, {}).get("name", "")
    void_flag  = fish_biome != biome

    title_parts = [f"{fish['emoji']} Caught a **{fish_name}**"]
    if void_flag:
        title_parts.append("⟵ 🌌 Void Tear!")
    if mut_name:
        title_parts.append(f"｜{mut['emoji']} **{mut_name} Mutation!**")

    embed = discord.Embed(
        title=" ".join(title_parts),
        color=0xFFD700 if mut_name else 0x00CFCF,
    )

    if mut_name:
        loot_lines = [
            f"💥 Auto-cashed: **+{mut_value:,} coins**",
            f"*(mutated × {mut['value_mult']:.0f} — {mut['desc']})*",
            f"✨ XP gained: **+{xp_gained}**",
        ]
    else:
        loot_lines = [f"Inventory: **{fish['emoji']} {fish_name}**", f"✨ XP gained: **+{xp_gained}**"]
    embed.add_field(name="📦 Loot", value="\n".join(loot_lines), inline=True)
    embed.add_field(
        name="📊 Progress",
        value=(
            f"Level **{p['level']}** — {get_title(p['level'])}\n"
            f"XP: {p['xp']}/{xp_needed(p['level'])}"
        ),
        inline=True,
    )

    # Extra catches
    extras = []
    if dup_fish_name:
        extras.append(f"🧲 **Duplicate!** Caught an extra {fish['emoji']} **{dup_fish_name}**")
    if echo_fish_name:
        efile = FISH_DATA.get(echo_fish_name, {})
        extras.append(f"⚡ **Echo!** Phantom cast snagged a {efile.get('emoji','🐟')} **{echo_fish_name}**")
    if bonus_fire_name:
        bfile = FISH_DATA.get(bonus_fire_name, {})
        extras.append(f"🔥 **Inferno!** A {bfile.get('emoji','🔥')} **{bonus_fire_name}** swam up from the deep")
    if extras:
        embed.add_field(name="⚡ Bonus Catches", value="\n".join(extras), inline=False)

    # Chests
    if chests_found:
        chest_lines = []
        for cr in chests_found:
            c = CHESTS[cr]
            prefix = "✨ Resonance" if (cr == "Uncommon" and special == "resonance" and chests_found.index(cr) == 0 and p["cast_count"] % 10 == 0) else c["emoji"]
            chest_lines.append(f"{prefix} **{cr} Chest** added to inventory!")
        embed.add_field(name="📦 Chest Found!", value="\n".join(chest_lines), inline=False)

    embed.set_footer(text=f"{biome_name} • {p['fish_count']} fish caught total • Cast #{p['cast_count']}")
    return embed, new_levels

def sell_all_fish(p: dict) -> tuple[discord.Embed | None, int]:
    inv = p.get("fish_inventory", {})
    if not inv:
        return None, 0
    buffs = get_player_buffs(p)
    coin_mult = 1 + buffs["coin_bonus"]
    total = 0
    lines = []
    for name in sorted(inv):
        count = inv[name]
        base_price = random.randint(*FISH_DATA[name]["value"]) if name in FISH_DATA else 50
        price = int(base_price * coin_mult)
        subtotal = price * count
        total += subtotal
        emoji = FISH_DATA[name]["emoji"] if name in FISH_DATA else "🐟"
        lines.append(f"{emoji} **{name}** ×{count} → **{subtotal:,} coins**")
    p["coins"] += total
    p["fish_inventory"] = {}
    embed = discord.Embed(title="💰 Fish Sold!", description="\n".join(lines), color=0xF1C40F)
    suffix = f" (+{int(buffs['coin_bonus']*100)}% Golden Net bonus)" if buffs["coin_bonus"] > 0 else ""
    embed.set_footer(text=f"Total earned: {total:,} coins{suffix}  |  Balance: {p['coins']:,} coins")
    return embed, total

# ═══════════════════════════════════════════════════════════════════════════════
#  UI — BUTTONS
# ═══════════════════════════════════════════════════════════════════════════════

class FishingView(discord.ui.View):
    def __init__(self, uid: int):
        super().__init__(timeout=180)
        self.uid = uid

    async def _check_owner(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.uid:
            await interaction.response.send_message("This isn't your fishing session!", ephemeral=True)
            return False
        return True

    @discord.ui.button(label="🎣 Fish Again", style=discord.ButtonStyle.primary)
    async def fish_again(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction):
            return
        p = get_player(self.uid)
        embed, new_levels = do_fish(p)
        save_data()
        level_up_embeds = _level_up_embeds(new_levels, p)
        view = FishingView(self.uid)
        await interaction.response.edit_message(embed=embed, view=view)
        for lvl_embed in level_up_embeds:
            await interaction.followup.send(embed=lvl_embed)

    @discord.ui.button(label="💰 Sell All Fish", style=discord.ButtonStyle.success)
    async def sell_fish(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not await self._check_owner(interaction):
            return
        p = get_player(self.uid)
        embed, total = sell_all_fish(p)
        if total == 0:
            return await interaction.response.send_message("🪣 Your fish inventory is empty!", ephemeral=True)
        save_data()
        view = FishingView(self.uid)
        await interaction.response.edit_message(embed=embed, view=view)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

def _level_up_embeds(new_levels: list[int], p: dict) -> list[discord.Embed]:
    embeds = []
    for lvl in new_levels:
        bonus = lvl * 150
        embed = discord.Embed(
            title=f"🎉 LEVEL UP! You're now Level {lvl}!",
            description=(
                f"**{get_title(lvl)}**\n\n"
                f"💰 Level bonus: **+{bonus:,} coins**\n"
                f"💵 Balance: **{p['coins']:,} coins**\n\n"
                f"Next level needs **{xp_needed(lvl):,} XP**"
            ),
            color=0xFFD700,
        )
        embeds.append(embed)
    return embeds

# ═══════════════════════════════════════════════════════════════════════════════
#  SLASH COMMANDS
# ═══════════════════════════════════════════════════════════════════════════════

# ─── /fish ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="fish", description="Cast your line in your current biome")
async def fish_cmd(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed, new_levels = do_fish(p)
    save_data()
    view = FishingView(interaction.user.id)
    await interaction.response.send_message(embed=embed, view=view)
    for lvl_embed in _level_up_embeds(new_levels, p):
        await interaction.followup.send(embed=lvl_embed)

# ─── /setbiome ────────────────────────────────────────────────────────────────
@bot.tree.command(name="setbiome", description="Choose where you fish")
@app_commands.describe(biome="river | lake | ocean | volcanic | arctic | abyss")
async def setbiome(interaction: discord.Interaction, biome: str):
    p = get_player(interaction.user.id)
    key = biome.strip().lower()
    if key not in BIOMES:
        opts = " | ".join(BIOMES.keys())
        return await interaction.response.send_message(f"❌ Unknown biome. Options: `{opts}`", ephemeral=True)
    bdata = BIOMES[key]
    if p["level"] < bdata["min_level"]:
        return await interaction.response.send_message(
            f"❌ **{bdata['name']}** requires Level **{bdata['min_level']}**. You are Level {p['level']}.", ephemeral=True
        )
    boat_tier = BOATS.get(p["boat"], BOATS["Rowboat"])["tier"]
    if boat_tier < bdata["min_boat_tier"]:
        needed_boat = next((n for n, d in BOATS.items() if d["tier"] == bdata["min_boat_tier"]), "better boat")
        return await interaction.response.send_message(
            f"❌ **{bdata['name']}** requires at least a **{needed_boat}**.", ephemeral=True
        )
    p["biome"] = key
    save_data()
    embed = discord.Embed(
        title=f"🗺️ Biome changed to {bdata['name']}",
        description=bdata["desc"],
        color=0x3498DB,
    )
    await interaction.response.send_message(embed=embed)

# ─── /sell ────────────────────────────────────────────────────────────────────
@bot.tree.command(name="sell", description="Sell all fish in your inventory")
async def sell_cmd(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed, total = sell_all_fish(p)
    if total == 0:
        return await interaction.response.send_message("🪣 Your fish inventory is empty!")
    save_data()
    await interaction.response.send_message(embed=embed)

# ─── /openchest ───────────────────────────────────────────────────────────────
@bot.tree.command(name="openchest", description="Open a chest from your inventory")
@app_commands.describe(rarity="common | uncommon | rare | epic | legendary (leave blank for highest rarity)")
async def openchest(interaction: discord.Interaction, rarity: str = ""):
    p = get_player(interaction.user.id)
    chests = p.get("chests", {})

    if rarity:
        key = rarity.strip().capitalize()
    else:
        # Open highest rarity available
        order = ["Legendary", "Epic", "Rare", "Uncommon", "Common"]
        key = next((r for r in order if chests.get(r, 0) > 0), None)

    if not key or chests.get(key, 0) == 0:
        chest_list = ", ".join(f"{v}× {k}" for k, v in chests.items() if v > 0) or "none"
        return await interaction.response.send_message(
            f"❌ You don't have that chest. Your chests: {chest_list}", ephemeral=True
        )

    chests[key] -= 1
    if chests[key] == 0:
        del chests[key]

    cdata = CHESTS[key]
    reward = random.randint(cdata["min_coins"], cdata["max_coins"])
    p["coins"] += reward
    save_data()

    embed = discord.Embed(
        title=f"{cdata['emoji']} {key} Chest Opened!",
        description=f"**+{reward:,} coins**\n💵 Balance: **{p['coins']:,} coins**",
        color=cdata["color"],
    )
    remaining = sum(v for v in chests.values())
    embed.set_footer(text=f"Chests remaining: {remaining}")
    await interaction.response.send_message(embed=embed)

# ─── /daily ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="daily", description="Claim your daily reward")
async def daily(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    buffs = get_player_buffs(p)
    now = datetime.now()
    last = datetime.fromisoformat(p["last_daily"]) if p["last_daily"] else None
    if last and (now - last) < timedelta(days=1):
        remaining = timedelta(days=1) - (now - last)
        h, rem = divmod(int(remaining.total_seconds()), 3600)
        m = rem // 60
        return await interaction.response.send_message(f"⏳ Come back in **{h}h {m}m**.")
    mult = 2 if buffs["double_daily"] else 1
    reward_coins = (500 + p["level"] * 25) * mult
    reward_xp    = (100 + p["level"] * 10) * mult
    p["coins"] += reward_coins
    p["xp"]    += reward_xp
    p["last_daily"] = now.isoformat()
    new_levels = check_level_up(p)
    save_data()
    double_note = " 📅 *(Double Daily active!)*" if mult == 2 else ""
    embed = discord.Embed(
        title="🎁 Daily Reward Claimed!",
        description=f"**+{reward_coins:,} coins** & **+{reward_xp} XP**{double_note}\n💵 Balance: **{p['coins']:,} coins**",
        color=0xF1C40F,
    )
    await interaction.response.send_message(embed=embed)
    for lvl_embed in _level_up_embeds(new_levels, p):
        await interaction.followup.send(embed=lvl_embed)

# ─── /rodshop ─────────────────────────────────────────────────────────────────
@bot.tree.command(name="rodshop", description="Browse all fishing rods")
async def rodshop(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed = discord.Embed(title="🎣 Rod Shop", description="Use `/buy rod <name>` to purchase.", color=0xE74C3C)
    for name, data in RODS.items():
        owned = "✅ **OWNED**" if p["rod"] == name else f"💰 {data['price']:,} coins"
        buffs_line = (
            f"🍀 Luck +{int(data['luck']*100)}%"
            f"  🎣 Dup +{int(data['dup']*100)}%"
            f"  ☢️ Mut +{int(data['mut']*100)}%"
        )
        embed.add_field(
            name=f"{data['emoji']} {name} Rod  (Tier {data['tier']})",
            value=f"{data['desc']}\nPower: **{data['power']}×**  |  {buffs_line}\n{owned}",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)

# ─── /baitshop ────────────────────────────────────────────────────────────────
@bot.tree.command(name="baitshop", description="Browse all bait types")
async def baitshop(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed = discord.Embed(title="🪱 Bait Shop", description="Use `/buy bait <name>` to purchase.", color=0x27AE60)
    for name, data in BAITS.items():
        owned = "✅ **OWNED**" if p["bait"] == name else f"💰 {data['price']:,} coins"
        embed.add_field(
            name=f"{data['emoji']} {name} Bait",
            value=f"{data['desc']}\nPower: **{data['power']}×** | {owned}",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)

# ─── /boatshop ────────────────────────────────────────────────────────────────
@bot.tree.command(name="boatshop", description="Browse all boats")
async def boatshop(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed = discord.Embed(title="🚤 Boat Shop", description="Use `/buy boat <name>` to purchase.", color=0x2980B9)
    for name, data in BOATS.items():
        owned = "✅ **OWNED**" if p["boat"] == name else f"💰 {data['price']:,} coins"
        embed.add_field(
            name=f"{data['emoji']} {name}  (Tier {data['tier']})",
            value=f"{data['desc']}\nPower: **{data['power']}×** | {owned}",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)

# ─── /biomeshop ───────────────────────────────────────────────────────────────
@bot.tree.command(name="biomeshop", description="View all fishing biomes and requirements")
async def biomeshop(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    embed = discord.Embed(title="🗺️ Biome Guide", description="Use `/setbiome <name>` to travel.", color=0x1ABC9C)
    for key, data in BIOMES.items():
        boat_name = next((n for n, d in BOATS.items() if d["tier"] == data["min_boat_tier"]), "?")
        unlocked = p["level"] >= data["min_level"] and BOATS.get(p["boat"], {}).get("tier", 1) >= data["min_boat_tier"]
        status = "✅ Unlocked" if unlocked else f"🔒 Lv{data['min_level']} + {boat_name}"
        current = " ← **HERE**" if p.get("biome") == key else ""
        embed.add_field(
            name=f"{data['name']}{current}",
            value=f"{data['desc']}\n{status}",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)

# ─── /buy ─────────────────────────────────────────────────────────────────────
@bot.tree.command(name="buy", description="Buy a rod, bait, or boat")
@app_commands.describe(
    category="rod | bait | boat",
    item="Name of the item (e.g. Crystal, Lucky, Yacht)",
)
async def buy(interaction: discord.Interaction, category: str, item: str):
    p = get_player(interaction.user.id)
    cat = category.strip().lower()
    item_key = item.strip().title()

    if cat == "rod":
        catalogue = RODS
        field = "rod"
    elif cat == "bait":
        catalogue = BAITS
        field = "bait"
    elif cat == "boat":
        catalogue = BOATS
        field = "boat"
    else:
        return await interaction.response.send_message("❌ Category must be `rod`, `bait`, or `boat`.", ephemeral=True)

    # Try exact match first, then partial
    entry = catalogue.get(item_key)
    if not entry:
        matches = [k for k in catalogue if item.strip().lower() in k.lower()]
        if len(matches) == 1:
            item_key = matches[0]
            entry = catalogue[item_key]
        elif len(matches) > 1:
            return await interaction.response.send_message(
                f"❌ Ambiguous: {', '.join(matches)}. Be more specific.", ephemeral=True
            )
        else:
            opts = ", ".join(catalogue.keys())
            return await interaction.response.send_message(
                f"❌ `{item}` not found in {cat} shop. Options: {opts}", ephemeral=True
            )

    if p[field] == item_key:
        return await interaction.response.send_message(f"✅ You already own **{item_key}**.", ephemeral=True)
    if entry["price"] == 0:
        return await interaction.response.send_message(f"❌ **{item_key}** is a starter item and cannot be bought.", ephemeral=True)
    if p["coins"] < entry["price"]:
        short = entry["price"] - p["coins"]
        return await interaction.response.send_message(
            f"❌ Not enough coins! You need **{short:,} more**.", ephemeral=True
        )

    p["coins"] -= entry["price"]
    p[field] = item_key
    save_data()

    embed = discord.Embed(
        title=f"✅ Purchased {entry['emoji']} {item_key}!",
        description=f"**-{entry['price']:,} coins** | Balance: **{p['coins']:,} coins**",
        color=0x2ECC71,
    )
    await interaction.response.send_message(embed=embed)

# ─── /powershop ───────────────────────────────────────────────────────────────
@bot.tree.command(name="powershop", description="Browse buyable passive power upgrades")
async def powershop(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    owned = p.get("powers", [])
    embed = discord.Embed(
        title="⚡ Power Shop",
        description="Passive upgrades that stack with your rod & bait.\nUse `/buypow <name>` to purchase. Each power is owned **once forever**.",
        color=0x9B59B6,
    )
    for name, data in POWERS.items():
        status = "✅ **OWNED**" if name in owned else f"💰 {data['price']:,} coins"
        bonuses = []
        if data["luck"]:        bonuses.append(f"🍀 +{int(data['luck']*100)}% luck")
        if data["dup"]:         bonuses.append(f"🎣 +{int(data['dup']*100)}% dup")
        if data["mut"]:         bonuses.append(f"☢️ +{int(data['mut']*100)}% mutation")
        if data["xp_bonus"]:    bonuses.append(f"✨ +{int(data['xp_bonus']*100)}% XP")
        if data["coin_bonus"]:  bonuses.append(f"💰 +{int(data['coin_bonus']*100)}% coins")
        if data["chest_bonus"]: bonuses.append(f"📦 +{int(data['chest_bonus']*100)}% chests")
        bonus_str = "  ".join(bonuses) if bonuses else data["desc"]
        embed.add_field(
            name=f"{data['emoji']} {name}",
            value=f"{data['desc']}\n{bonus_str}\n{status}",
            inline=False,
        )
    await interaction.response.send_message(embed=embed)

# ─── /buypow ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="buypow", description="Buy a passive power upgrade")
@app_commands.describe(name="Name of the power (e.g. Lucky Charm, XP Tome)")
async def buypow(interaction: discord.Interaction, name: str):
    p = get_player(interaction.user.id)
    # Flexible name matching
    key = name.strip().title()
    if key not in POWERS:
        matches = [k for k in POWERS if name.strip().lower() in k.lower()]
        if len(matches) == 1:
            key = matches[0]
        elif len(matches) > 1:
            return await interaction.response.send_message(
                f"❌ Ambiguous: {', '.join(matches)}. Be more specific.", ephemeral=True
            )
        else:
            opts = ", ".join(POWERS.keys())
            return await interaction.response.send_message(
                f"❌ `{name}` not found. Options: {opts}", ephemeral=True
            )
    if key in p.get("powers", []):
        return await interaction.response.send_message(f"✅ You already own **{key}**.", ephemeral=True)
    pw = POWERS[key]
    if p["coins"] < pw["price"]:
        short = pw["price"] - p["coins"]
        return await interaction.response.send_message(
            f"❌ You need **{short:,} more coins** to buy **{key}**.", ephemeral=True
        )
    p["coins"] -= pw["price"]
    p.setdefault("powers", []).append(key)
    save_data()
    embed = discord.Embed(
        title=f"✅ {pw['emoji']} {key} Activated!",
        description=f"**-{pw['price']:,} coins** | Balance: **{p['coins']:,} coins**\n\n*{pw['desc']}*",
        color=0x9B59B6,
    )
    await interaction.response.send_message(embed=embed)

# ─── /inventory ───────────────────────────────────────────────────────────────
@bot.tree.command(name="inventory", description="View your full profile and fish collection")
async def inventory(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    rod   = RODS.get(p["rod"],  RODS["Wooden"])
    bait  = BAITS.get(p["bait"], BAITS["Basic"])
    boat  = BOATS.get(p["boat"], BOATS["Rowboat"])
    biome = BIOMES.get(p.get("biome", "river"), BIOMES["river"])
    power = player_power(p)
    buffs = get_player_buffs(p)

    embed = discord.Embed(
        title=f"🎒 {interaction.user.display_name}'s Profile",
        color=0x3498DB,
    )
    embed.add_field(
        name="📊 Stats",
        value=(
            f"**{get_title(p['level'])}** — Level **{p['level']}**\n"
            f"XP: **{p['xp']:,}** / **{xp_needed(p['level']):,}**\n"
            f"💰 Coins: **{p['coins']:,}**\n"
            f"🐟 Total Fish: **{p['fish_count']}**  |  Cast #**{p.get('cast_count', 0)}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="⚙️ Gear",
        value=(
            f"{rod['emoji']} **{p['rod']} Rod** (×{rod['power']})\n"
            f"{bait['emoji']} **{p['bait']} Bait** (×{bait['power']})\n"
            f"{boat['emoji']} **{p['boat']}** (×{boat['power']})\n"
            f"⚡ Total Power: **{power:.2f}×**\n"
            f"📍 Biome: **{biome['name']}**"
        ),
        inline=True,
    )

    # Aggregated buffs
    embed.add_field(
        name="🌟 Active Buffs",
        value=(
            f"🍀 Luck: **+{int(buffs['luck']*100)}%**\n"
            f"🎣 Duplicate: **+{int(buffs['dup']*100)}%**\n"
            f"☢️ Mutation: **+{int(buffs['mut']*100)}%**\n"
            f"✨ XP Bonus: **+{int(buffs['xp_bonus']*100)}%**\n"
            f"💰 Coin Bonus: **+{int(buffs['coin_bonus']*100)}%**\n"
            f"📦 Chest Luck: **+{int(buffs['chest_bonus']*100)}%**"
        ),
        inline=True,
    )

    # Powers
    owned_powers = p.get("powers", [])
    if owned_powers:
        pw_lines = [f"{POWERS[pw]['emoji']} **{pw}**" for pw in owned_powers if pw in POWERS]
        embed.add_field(name="⚡ Powers", value="\n".join(pw_lines), inline=False)

    # Chests
    chest_inv = p.get("chests", {})
    if chest_inv:
        chest_lines = [f"{CHESTS[k]['emoji']} **{k}** ×{v}" for k, v in chest_inv.items() if v > 0]
        embed.add_field(name="📦 Chests", value="\n".join(chest_lines), inline=False)

    # Fish inventory
    fish_inv = p.get("fish_inventory", {})
    if fish_inv:
        lines = []
        total_value = 0
        coin_mult = 1 + buffs["coin_bonus"]
        for name in sorted(fish_inv):
            count = fish_inv[name]
            fdata = FISH_DATA.get(name, {})
            price = int(sum(fdata.get("value", (50, 50))) // 2 * coin_mult) * count
            total_value += price
            emoji = fdata.get("emoji", "🐟")
            lines.append(f"{emoji} **{name}** ×{count}")
        lines.append(f"\n💰 Est. sell value: **~{total_value:,} coins**")
        embed.add_field(name="🐠 Fish Inventory", value="\n".join(lines), inline=False)
    else:
        embed.add_field(name="🐠 Fish Inventory", value="*Empty — go `/fish`!*", inline=False)

    await interaction.response.send_message(embed=embed)

# ─── /leaderboard ─────────────────────────────────────────────────────────────
@bot.tree.command(name="leaderboard", description="Top players by level")
async def leaderboard(interaction: discord.Interaction):
    sorted_p = sorted(players.items(), key=lambda x: (x[1].get("level", 1), x[1].get("xp", 0)), reverse=True)[:10]
    embed = discord.Embed(title="🏆 Leaderboard", color=0xF39C12)
    medals = ["🥇", "🥈", "🥉"]
    lines = []
    for rank, (uid, data) in enumerate(sorted_p, 1):
        medal = medals[rank - 1] if rank <= 3 else f"**{rank}.**"
        title = get_title(data.get("level", 1))
        lines.append(
            f"{medal} <@{uid}> — {title} Lv**{data.get('level', 1)}** "
            f"| 🐟 {data.get('fish_count', 0)} | 💰 {data.get('coins', 0):,}"
        )
    embed.description = "\n".join(lines) if lines else "No players yet!"
    await interaction.response.send_message(embed=embed)

# ─── /gamble ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="gamble", description="Bet coins on a coin flip (48% win chance)")
@app_commands.describe(amount="Amount of coins to bet")
async def gamble(interaction: discord.Interaction, amount: int):
    p = get_player(interaction.user.id)
    if amount <= 0:
        return await interaction.response.send_message("❌ Bet must be greater than 0.", ephemeral=True)
    if amount > p["coins"]:
        return await interaction.response.send_message(f"❌ You only have **{p['coins']:,} coins**.", ephemeral=True)
    win = random.random() < 0.48
    if win:
        p["coins"] += amount
        embed = discord.Embed(title="🎰 You Won!", description=f"**+{amount:,} coins** | Balance: **{p['coins']:,}**", color=0x2ECC71)
    else:
        p["coins"] -= amount
        embed = discord.Embed(title="🎰 You Lost!", description=f"**-{amount:,} coins** | Balance: **{p['coins']:,}**", color=0xE74C3C)
    save_data()
    await interaction.response.send_message(embed=embed)

# ─── /play & /closeplay ───────────────────────────────────────────────────────

class CloseChannelView(discord.ui.View):
    def __init__(self, owner_id: int):
        super().__init__(timeout=None)  # persist until clicked
        self.owner_id = owner_id

    @discord.ui.button(label="🗑️ Close Channel", style=discord.ButtonStyle.danger)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Only the channel owner or admins can close it
        is_owner = interaction.user.id == self.owner_id
        is_admin = interaction.user.guild_permissions.administrator
        if not is_owner and not is_admin:
            return await interaction.response.send_message(
                "❌ Only the channel owner or an admin can close this.", ephemeral=True
            )
        await interaction.response.send_message("👋 Closing channel in 3 seconds…")
        import asyncio
        await asyncio.sleep(3)
        # Clear saved channel ID from player data
        p = players.get(str(self.owner_id))
        if p:
            p["play_channel_id"] = None
            save_data()
        await interaction.channel.delete(reason="Play channel closed by user")

@bot.tree.command(name="play", description="Open your private fishing workspace channel")
async def play_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message(
            "❌ This command only works inside a server.", ephemeral=True
        )

    p = get_player(interaction.user.id)
    guild = interaction.guild

    # Check if a channel already exists for this player
    existing_id = p.get("play_channel_id")
    if existing_id:
        existing = guild.get_channel(existing_id)
        if existing:
            return await interaction.response.send_message(
                f"You already have a play channel: {existing.mention}\nUse `/closeplay` to delete it first.",
                ephemeral=True,
            )
        # Channel was deleted externally — clear the stale ID
        p["play_channel_id"] = None

    await interaction.response.defer(ephemeral=True)

    # Deny everyone by default; grant access to the invoking user and all admin/staff roles
    overwrites = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        interaction.user:   discord.PermissionOverwrite(
            view_channel=True, send_messages=True, read_message_history=True
        ),
        guild.me: discord.PermissionOverwrite(
            view_channel=True, send_messages=True, manage_channels=True
        ),
    }
    for role in guild.roles:
        if role.is_default():
            continue
        if role.permissions.administrator or role.permissions.manage_guild:
            overwrites[role] = discord.PermissionOverwrite(
                view_channel=True, send_messages=True, read_message_history=True
            )

    safe_name = "".join(c if c.isalnum() or c in "-_" else "-" for c in interaction.user.name.lower())
    channel = await guild.create_text_channel(
        name=f"play-{safe_name}",
        overwrites=overwrites,
        topic=f"🎣 Private workspace for {interaction.user.display_name}",
        reason="Player opened their private play channel",
    )

    p["play_channel_id"] = channel.id
    save_data()

    # Welcome embed inside the new channel
    rod   = RODS.get(p["rod"],  RODS["Wooden"])
    bait  = BAITS.get(p["bait"], BAITS["Basic"])
    boat  = BOATS.get(p["boat"], BOATS["Rowboat"])
    power = player_power(p)
    embed = discord.Embed(
        title=f"🎣 Welcome to your private workspace, {interaction.user.display_name}!",
        description=(
            "This channel is visible only to you and server staff.\n"
            "All your fishing commands work here.\n\n"
            f"**{get_title(p['level'])}** — Level **{p['level']}**\n"
            f"💰 Coins: **{p['coins']:,}**  |  🐟 Fish caught: **{p['fish_count']}**\n"
            f"⚡ Power: **{power:.2f}×**\n\n"
            f"{rod['emoji']} **{p['rod']} Rod** · {bait['emoji']} **{p['bait']} Bait** · {boat['emoji']} **{p['boat']}**"
        ),
        color=0x2ECC71,
    )
    embed.set_footer(text="Use the button below to close this channel when you're done.")
    view = CloseChannelView(owner_id=interaction.user.id)
    await channel.send(content=interaction.user.mention, embed=embed, view=view)

    await interaction.followup.send(
        f"✅ Your private channel is ready: {channel.mention}", ephemeral=True
    )

@bot.tree.command(name="closeplay", description="Delete your private play channel")
async def closeplay_cmd(interaction: discord.Interaction):
    if interaction.guild is None:
        return await interaction.response.send_message("❌ Server-only command.", ephemeral=True)

    p = get_player(interaction.user.id)
    channel_id = p.get("play_channel_id")
    if not channel_id:
        return await interaction.response.send_message(
            "❌ You don't have an open play channel.", ephemeral=True
        )

    channel = interaction.guild.get_channel(channel_id)
    p["play_channel_id"] = None
    save_data()

    if channel:
        await interaction.response.send_message("👋 Closing your play channel…", ephemeral=True)
        await channel.delete(reason="Player closed their play channel via /closeplay")
    else:
        await interaction.response.send_message(
            "✅ Channel record cleared (channel was already deleted).", ephemeral=True
        )

# ─── /reset ───────────────────────────────────────────────────────────────────

class ConfirmResetAllView(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=30)

    @discord.ui.button(label="✅ Yes, reset everyone", style=discord.ButtonStyle.danger)
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        players.clear()
        save_data()
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(
            content="♻️ **All player data has been reset.**",
            view=self,
        )

    @discord.ui.button(label="❌ Cancel", style=discord.ButtonStyle.secondary)
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        for child in self.children:
            child.disabled = True
        await interaction.response.edit_message(content="Reset cancelled.", view=self)

    async def on_timeout(self):
        for child in self.children:
            child.disabled = True

@bot.tree.command(name="reset", description="[Admin] Reset a player's data or wipe everyone")
@app_commands.describe(
    target="'all' to wipe everyone, or @mention / user ID for one player",
)
@app_commands.checks.has_permissions(administrator=True)
async def reset(interaction: discord.Interaction, target: str):
    if target.strip().lower() == "all":
        view = ConfirmResetAllView()
        await interaction.response.send_message(
            "⚠️ **Are you sure?** This will permanently delete ALL player data.",
            view=view,
            ephemeral=True,
        )
        return

    # Try to extract a user ID from a mention (<@123>) or raw ID
    uid = target.strip().lstrip("<@!").rstrip(">")
    if not uid.isdigit():
        return await interaction.response.send_message(
            "❌ Provide `all` or a valid @mention / user ID.", ephemeral=True
        )

    if uid not in players:
        return await interaction.response.send_message(
            f"❌ No data found for user `{uid}`.", ephemeral=True
        )

    del players[uid]
    save_data()
    await interaction.response.send_message(
        f"♻️ Data for <@{uid}> has been reset.", ephemeral=True
    )

# ─── /purge ───────────────────────────────────────────────────────────────────
@bot.tree.command(name="purge", description="[Admin] Delete messages from this channel")
@app_commands.checks.has_permissions(manage_messages=True)
async def purge(interaction: discord.Interaction, amount: int):
    if not 1 <= amount <= 100:
        return await interaction.response.send_message("❌ Amount must be 1–100.", ephemeral=True)
    await interaction.response.defer(ephemeral=True)
    deleted = await interaction.channel.purge(limit=amount)
    await interaction.followup.send(f"🗑️ Deleted **{len(deleted)} messages**.", ephemeral=True)

# ─── /verify ──────────────────────────────────────────────────────────────────
@bot.tree.command(name="verify", description="Set up your account and start playing")
async def verify(interaction: discord.Interaction):
    p = get_player(interaction.user.id)
    save_data()
    embed = discord.Embed(
        title="✅ Account Ready!",
        description=(
            f"Welcome, **{interaction.user.display_name}**!\n\n"
            f"💰 Starting coins: **{p['coins']:,}**\n"
            f"🪵 Rod: **{p['rod']}** | 🪱 Bait: **{p['bait']}** | 🚣 Boat: **{p['boat']}**\n"
            f"📍 Biome: **{BIOMES[p['biome']]['name']}**\n\n"
            "**Quick Start:**\n"
            "`/fish` → catch fish\n"
            "`/sell` → sell your catch\n"
            "`/rodshop` `/baitshop` `/boatshop` → upgrade gear\n"
            "`/setbiome` → travel to new waters\n"
            "`/openchest` → open chests you find"
        ),
        color=0x2ECC71,
    )
    await interaction.response.send_message(embed=embed)

# ─── /daily ───────────────────────────────────────────────────────────────────
# (defined above)

# ═══════════════════════════════════════════════════════════════════════════════
#  ERROR HANDLER
# ═══════════════════════════════════════════════════════════════════════════════
@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError):
    if isinstance(error, app_commands.MissingPermissions):
        msg = "❌ You don't have permission to use this command."
    else:
        logger.error(f"Command error: {error}", exc_info=error)
        msg = "⚠️ Something went wrong. Please try again."
    try:
        if interaction.response.is_done():
            await interaction.followup.send(msg, ephemeral=True)
        else:
            await interaction.response.send_message(msg, ephemeral=True)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
#  STARTUP
# ═══════════════════════════════════════════════════════════════════════════════
@bot.event
async def on_ready():
    print(f"Logged in as {bot.user} — EPIC Fishing Adventure Bot is Online!")
    # Sync to every guild the bot is in for instant command propagation
    synced = 0
    for guild in bot.guilds:
        try:
            bot.tree.copy_global_to(guild=guild)
            await bot.tree.sync(guild=guild)
            synced += 1
        except Exception as e:
            logger.warning(f"Failed to sync guild {guild.id}: {e}")
    print(f"Slash commands synced to {synced} guild(s).")

async def setup_hook():
    # Global sync for any new guilds the bot joins later
    await bot.tree.sync()

bot.setup_hook = setup_hook

token = os.environ.get("DISCORD_BOT_TOKEN")
if not token:
    raise RuntimeError("DISCORD_BOT_TOKEN secret is not set.")

bot.run(token)
