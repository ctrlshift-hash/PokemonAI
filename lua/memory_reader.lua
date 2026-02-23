-- Pokemon FireRed v1.0 (US) Memory Reader for mGBA
-- Load via: Tools > Scripting > Load Script
-- Reads RAM every 30 frames and writes data/game_state.json

-- ═══════════════════════════════════════════════════════════
-- Minimal JSON Encoder (mGBA has no built-in JSON library)
-- ═══════════════════════════════════════════════════════════

local function json_escape(s)
    s = s:gsub("\\", "\\\\")
    s = s:gsub('"', '\\"')
    s = s:gsub("\n", "\\n")
    s = s:gsub("\r", "\\r")
    s = s:gsub("\t", "\\t")
    return s
end

local function json_encode(val)
    local t = type(val)
    if val == nil then
        return "null"
    elseif t == "boolean" then
        return val and "true" or "false"
    elseif t == "number" then
        return tostring(val)
    elseif t == "string" then
        return '"' .. json_escape(val) .. '"'
    elseif t == "table" then
        -- Check if array (sequential integer keys starting at 1)
        local is_array = true
        local max_idx = 0
        for k, _ in pairs(val) do
            if type(k) ~= "number" or k ~= math.floor(k) or k < 1 then
                is_array = false
                break
            end
            if k > max_idx then max_idx = k end
        end
        if is_array and max_idx == #val then
            local parts = {}
            for i = 1, #val do
                parts[i] = json_encode(val[i])
            end
            return "[" .. table.concat(parts, ",") .. "]"
        else
            local parts = {}
            for k, v in pairs(val) do
                local key = type(k) == "string" and k or tostring(k)
                parts[#parts + 1] = '"' .. json_escape(key) .. '":' .. json_encode(v)
            end
            return "{" .. table.concat(parts, ",") .. "}"
        end
    end
    return "null"
end

-- ═══════════════════════════════════════════════════════════
-- Bitwise helpers (compatible with mGBA Lua 5.4)
-- ═══════════════════════════════════════════════════════════

local function bxor(a, b)
    -- Use Lua 5.3+ bitwise XOR
    return a ~ b
end

local function band(a, b)
    return a & b
end

local function rshift(a, n)
    return a >> n
end

-- ═══════════════════════════════════════════════════════════
-- FireRed v1.0 US RAM Addresses
-- ═══════════════════════════════════════════════════════════

local ADDR = {
    PLAYER_X     = 0x02037078,  -- 2 bytes
    PLAYER_Y     = 0x0203707A,  -- 2 bytes
    MAP_ID       = 0x02031DBC,  -- 1 byte
    MONEY        = 0x02025F04,  -- 4 bytes
    BADGES       = 0x02025F00,  -- 1 byte (each bit = 1 badge)
    PARTY_COUNT  = 0x02024029,  -- 1 byte
    PARTY_BASE   = 0x02024284,  -- each Pokemon struct is 100 bytes
    IN_BATTLE    = 0x030030F0,  -- 0=none, 1=wild, 2=trainer
    POKEDEX_SEEN   = 0x02025F2C,  -- 52 bytes, bit flags
    POKEDEX_CAUGHT = 0x02025F60,  -- 52 bytes, bit flags
}

-- Unencrypted battle stat offsets (within each 100-byte party slot)
local PKM = {
    PID      = 0x00,  -- 4 bytes (Personality Value)
    OTID     = 0x04,  -- 4 bytes (Original Trainer ID)
    DATA     = 0x20,  -- 48 bytes (4 encrypted substructures, 12 bytes each)
    STATUS   = 0x50,  -- 4 bytes
    LEVEL    = 0x54,  -- 1 byte
    HP_CUR   = 0x56,  -- 2 bytes
    HP_MAX   = 0x58,  -- 2 bytes
}

local PARTY_SLOT_SIZE = 100

-- ═══════════════════════════════════════════════════════════
-- Gen 3 Party Data Decryption
-- Pokemon data at 0x20-0x4F is encrypted with PID XOR OTID.
-- The 4 substructures (Growth, Attacks, EVs, Misc) are
-- reordered based on PID % 24.
-- ═══════════════════════════════════════════════════════════

-- For each PID%24 value, which slot (0-3) contains Growth substructure
local GROWTH_SLOT = {
    [0]=0, [1]=0, [2]=0, [3]=0, [4]=0, [5]=0,
    [6]=1, [7]=1, [8]=2, [9]=3, [10]=2, [11]=3,
    [12]=1, [13]=1, [14]=2, [15]=3, [16]=2, [17]=3,
    [18]=1, [19]=1, [20]=2, [21]=3, [22]=2, [23]=3,
}

-- For each PID%24 value, which slot (0-3) contains Attacks substructure
local ATTACKS_SLOT = {
    [0]=1, [1]=1, [2]=2, [3]=2, [4]=3, [5]=3,
    [6]=0, [7]=0, [8]=0, [9]=0, [10]=0, [11]=0,
    [12]=2, [13]=3, [14]=1, [15]=1, [16]=3, [17]=2,
    [18]=2, [19]=3, [20]=1, [21]=1, [22]=3, [23]=2,
}

-- Mask to 32 bits (Lua 5.4 uses 64-bit integers, read32 may sign-extend)
local function u32(v)
    return v & 0xFFFFFFFF
end

-- Decrypt one 12-byte substructure (3 x 32-bit words) and return them
local function decrypt_substruct(base, slot, key)
    local offset = base + PKM.DATA + (slot * 12)
    local w0 = u32(bxor(u32(emu:read32(offset + 0)), key))
    local w1 = u32(bxor(u32(emu:read32(offset + 4)), key))
    local w2 = u32(bxor(u32(emu:read32(offset + 8)), key))
    return w0, w1, w2
end

-- ═══════════════════════════════════════════════════════════
-- Helper: Count set bits in a byte range (for pokedex)
-- ═══════════════════════════════════════════════════════════

local function count_bits(start_addr, num_bytes)
    local count = 0
    for i = 0, num_bytes - 1 do
        local byte = emu:read8(start_addr + i)
        while byte > 0 do
            count = count + (byte % 2)
            byte = math.floor(byte / 2)
        end
    end
    return count
end

-- ═══════════════════════════════════════════════════════════
-- Helper: Count badge bits
-- ═══════════════════════════════════════════════════════════

local function count_badges(badge_byte)
    local count = 0
    while badge_byte > 0 do
        count = count + (badge_byte % 2)
        badge_byte = math.floor(badge_byte / 2)
    end
    return count
end

-- ═══════════════════════════════════════════════════════════
-- Read full game state from RAM
-- ═══════════════════════════════════════════════════════════

local function read_game_state()
    local state = {}

    -- Player position
    state.player_x = emu:read16(ADDR.PLAYER_X)
    state.player_y = emu:read16(ADDR.PLAYER_Y)
    state.map_id = emu:read8(ADDR.MAP_ID)

    -- Money (stored as BCD in FireRed, read as raw 4 bytes)
    state.money = emu:read32(ADDR.MONEY)

    -- Badges
    local badge_byte = emu:read8(ADDR.BADGES)
    -- Clamp to valid range (0-255, but only lower 8 bits matter)
    state.badges = badge_byte
    state.badge_count = count_badges(badge_byte)

    -- Battle state
    local battle_raw = emu:read8(ADDR.IN_BATTLE)
    -- Only 0=none, 1=wild, 2=trainer are valid; treat anything else as 0
    if battle_raw == 1 or battle_raw == 2 then
        state.in_battle = battle_raw
    else
        state.in_battle = 0
    end

    -- Party
    local party_count = emu:read8(ADDR.PARTY_COUNT)
    if party_count > 6 then party_count = 6 end
    state.party_count = party_count

    state.party = {}
    for i = 0, party_count - 1 do
        local base = ADDR.PARTY_BASE + (i * PARTY_SLOT_SIZE)
        local pokemon = {}

        -- Read PID and OT ID for decryption (mask to 32 bits for Lua 5.4)
        local pid = u32(emu:read32(base + PKM.PID))
        local otid = u32(emu:read32(base + PKM.OTID))
        local key = u32(bxor(pid, otid))

        -- Determine substructure order
        local p = pid % 24

        -- Decrypt Growth substructure: species (16 bits), item (16 bits), xp (32 bits)
        local g0, g1, g2 = decrypt_substruct(base, GROWTH_SLOT[p], key)
        pokemon.species = band(g0, 0xFFFF)
        pokemon.xp = g1

        -- Decrypt Attacks substructure: move1-4 (16 bits each)
        local a0, a1, a2 = decrypt_substruct(base, ATTACKS_SLOT[p], key)
        pokemon.moves = {
            band(a0, 0xFFFF),
            band(rshift(a0, 16), 0xFFFF),
            band(a1, 0xFFFF),
            band(rshift(a1, 16), 0xFFFF),
        }

        -- Read unencrypted battle stats (offsets 0x50+)
        pokemon.level = emu:read8(base + PKM.LEVEL)
        pokemon.hp_current = emu:read16(base + PKM.HP_CUR)
        pokemon.hp_max = emu:read16(base + PKM.HP_MAX)
        pokemon.status = emu:read8(base + PKM.STATUS)

        -- Only include if species is valid (1-411 for Gen 3)
        if pokemon.species > 0 and pokemon.species <= 411 then
            state.party[#state.party + 1] = pokemon
        else
            console:log("Party slot " .. i .. ": invalid species " .. pokemon.species .. " (PID=" .. pid .. " OTID=" .. otid .. ")")
        end
    end

    -- Pokedex counts
    state.pokedex_seen = count_bits(ADDR.POKEDEX_SEEN, 52)
    state.pokedex_caught = count_bits(ADDR.POKEDEX_CAUGHT, 52)

    return state
end

-- ═══════════════════════════════════════════════════════════
-- Write JSON to file
-- ═══════════════════════════════════════════════════════════

local script_dir = ""

-- Absolute path so it works regardless of mGBA's working directory
local OUTPUT_PATH = "C:/Users/Vigan/OneDrive/Desktop/github-projects/PokemonAI/data/game_state.json"

local frame_counter = 0

local function on_frame()
    frame_counter = frame_counter + 1

    -- Read every 30 frames (~0.5 seconds at 60fps)
    if frame_counter % 30 ~= 0 then
        return
    end

    local state = read_game_state()
    local json_str = json_encode(state)

    local file = io.open(OUTPUT_PATH, "w")
    if file then
        file:write(json_str)
        file:close()
    end
end

-- Register the frame callback
callbacks:add("frame", on_frame)

console:log("Pokemon FireRed Memory Reader loaded!")
console:log("Writing game state to: " .. OUTPUT_PATH)
console:log("Reading every 30 frames (~0.5s)")
