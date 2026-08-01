/* ---- Texture character & material presets ---- */

typedef enum sc_tex_character {
    SC_TEX_SMOOTH = 0,  /* wide clusters, few large signals */
    SC_TEX_BUMPY  = 1,  /* small tight clusters, many, small signal */
    SC_TEX_ROCKY  = 2   /* variable signal, wide + many clusters */
} sc_tex_character;

typedef enum sc_tex_preset {
    SC_PRESET_OFFICE_CARPET = 0,
    SC_PRESET_WALLPAPER,
    SC_PRESET_BRICK,
    SC_PRESET_PEBBLE_FLOOR,
    SC_PRESET_TILE,
    SC_PRESET_ROCK_WALL,
    SC_PRESET_SHAG_CARPET,
    SC_PRESET_RUG,
    SC_PRESET_LIQUID,
    SC_PRESET_CUSTOM
} sc_tex_preset;

typedef struct sc_tex_profile {
    sc_tex_character character;
    sc_tex_preset    preset;
    float cluster_radius;     /* world units */
    float signal_distance;    /* jS */
    float jitter_amp;
    uint32_t cluster_count;
    sc_def_layer layer;
    float opacity;
    char name[48];
} sc_tex_profile;

static inline sc_tex_profile sc_tex_profile_for(sc_tex_preset p) {
    sc_tex_profile pr;
    memset(&pr, 0, sizeof(pr));
    pr.preset = p;
    pr.layer = SC_DEF_HD_TEXTURE;
    pr.opacity = 1.0f;

    switch (p) {
    case SC_PRESET_OFFICE_CARPET:
        pr.character = SC_TEX_BUMPY;
        strncpy(pr.name, "office_carpet", 47);
        pr.cluster_radius = 0.22f; pr.signal_distance = 0.55f;
        pr.jitter_amp = 0.10f; pr.cluster_count = 28;
        pr.layer = SC_DEF_HD_TEXTURE;
        break;
    case SC_PRESET_WALLPAPER:
        pr.character = SC_TEX_SMOOTH;
        strncpy(pr.name, "wallpaper", 47);
        pr.cluster_radius = 0.85f; pr.signal_distance = 2.40f;
        pr.jitter_amp = 0.04f; pr.cluster_count = 6;
        pr.layer = SC_DEF_INNER_TEXTURE;
        break;
    case SC_PRESET_BRICK:
        pr.character = SC_TEX_ROCKY;
        strncpy(pr.name, "brick", 47);
        pr.cluster_radius = 0.70f; pr.signal_distance = 1.10f;
        pr.jitter_amp = 0.18f; pr.cluster_count = 14;
        pr.layer = SC_DEF_OUTER_TEXTURE;
        break;
    case SC_PRESET_PEBBLE_FLOOR:
        pr.character = SC_TEX_ROCKY;
        strncpy(pr.name, "pebble_floor", 47);
        pr.cluster_radius = 0.45f; pr.signal_distance = 0.90f;
        pr.jitter_amp = 0.22f; pr.cluster_count = 20;
        break;
    case SC_PRESET_TILE:
        pr.character = SC_TEX_SMOOTH;
        strncpy(pr.name, "tile", 47);
        pr.cluster_radius = 1.10f; pr.signal_distance = 2.80f;
        pr.jitter_amp = 0.03f; pr.cluster_count = 4;
        pr.layer = SC_DEF_HD_LIGHT;
        break;
    case SC_PRESET_ROCK_WALL:
        pr.character = SC_TEX_ROCKY;
        strncpy(pr.name, "rock_wall", 47);
        pr.cluster_radius = 0.95f; pr.signal_distance = 1.40f;
        pr.jitter_amp = 0.28f; pr.cluster_count = 16;
        pr.layer = SC_DEF_OUTER_TEXTURE;
        break;
    case SC_PRESET_SHAG_CARPET:
        pr.character = SC_TEX_BUMPY;
        strncpy(pr.name, "shag_carpet", 47);
        pr.cluster_radius = 0.18f; pr.signal_distance = 0.40f;
        pr.jitter_amp = 0.16f; pr.cluster_count = 36;
        break;
    case SC_PRESET_RUG:
        pr.character = SC_TEX_BUMPY;
        strncpy(pr.name, "rug", 47);
        pr.cluster_radius = 0.30f; pr.signal_distance = 0.65f;
        pr.jitter_amp = 0.12f; pr.cluster_count = 22;
        break;
    case SC_PRESET_LIQUID:
        pr.character = SC_TEX_SMOOTH;
        strncpy(pr.name, "liquid", 47);
        pr.cluster_radius = 1.40f; pr.signal_distance = 3.20f;
        pr.jitter_amp = 0.35f; pr.cluster_count = 5;
        pr.layer = SC_DEF_HD_LIGHT;
        break;
    default:
        pr.character = SC_TEX_BUMPY;
        strncpy(pr.name, "custom", 47);
        pr.cluster_radius = 0.50f; pr.signal_distance = 1.20f;
        pr.jitter_amp = 0.15f; pr.cluster_count = 12;
        break;
    }
    return pr;
}

/* Apply character bias on top of a profile (smooth / bumpy / rocky) */
static inline void sc_tex_apply_character(sc_tex_profile* pr, sc_tex_character c) {
    pr->character = c;
    switch (c) {
    case SC_TEX_SMOOTH:
        pr->cluster_radius *= 1.6f;
        pr->signal_distance *= 1.8f;
        pr->cluster_count = (pr->cluster_count > 4) ? pr->cluster_count / 3 : 2;
        pr->jitter_amp *= 0.5f;
        break;
    case SC_TEX_BUMPY:
        pr->cluster_radius *= 0.55f;
        pr->signal_distance *= 0.6f;
        pr->cluster_count = pr->cluster_count * 2 + 4;
        pr->jitter_amp *= 1.1f;
        break;
    case SC_TEX_ROCKY:
        pr->cluster_radius *= 1.25f;
        pr->signal_distance *= 0.95f;
        pr->cluster_count = pr->cluster_count + pr->cluster_count / 2;
        pr->jitter_amp *= 1.4f;
        break;
    }
}
