/* light_lab.c  –  SignalCloud-style illuminosity lab
 * Compile:  gcc -std=c11 -O2 -lm -o light_lab light_lab.c
 * Run:      ./light_lab
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#include <stdint.h>
#include <stdbool.h>
#include <time.h>

#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif

/* ------------------------------------------------------------------ */
/*  Data structures matching the notes                                 */
/* ------------------------------------------------------------------ */

typedef struct { float x, y, z; } Vec3;

typedef struct {
    Vec3   pos;           /* +  point of light source                  */
    float  radius;        /* ○  radius of light source                 */
    float  i_pct;         /* i% illuminosity (no hard upper limit)     */
    Vec3   color;         /* L0 light-source colour                    */
    Vec3   target;        /* direction the “source ray” is aimed       */
    bool   is_global;     /* true = G0 / day-night global              */
    bool   selected;
    char   name[32];
} LightSource;

typedef struct {
    Vec3   pos;           /* aperture centre                           */
    float  distance;      /* AP aperture distance                      */
    Vec3   color;         /* L1 aperture colour                        */
    float  half_width;    /* opening half-width                        */
    float  bottom_y, top_y;
} Aperture;

typedef struct {
    /* quality tiers (your distance bands) */
    float darkness;       /* 0-3   “NO LIGHT”                          */
    float outline;        /* 4-29  outlines & silhouettes (¼ dist)     */
    float low_half;       /* 30-45 low light (½ dist)                  */
    float low_norm;       /* 46-65 low light (normal dist)             */
    float good;           /* 66-77 good light                          */
    float great;          /* 78-89 great light                         */
    float best;           /* 90-110 best                               */
    float boost;          /* 111+  best w/ distance boost              */
} QualityBands;

typedef struct {
    /* day / night split                                               */
    Vec3   day_color;
    float  day_i;
    Vec3   night_color;
    float  night_i;
    float  day_to_night_s; /* left scrollbar  – 30 … 90 s              */
    float  night_to_day_s; /* right scrollbar – 30 … 90 s              */
    float  time_of_day;    /* 0 = midnight, 0.5 = noon, 1 = next mid   */
    bool   playing;
    bool   paused;
} DayNightCycle;

/* ------------------------------------------------------------------ */
/*  Constants from the notes                                           */
/* ------------------------------------------------------------------ */

#define MAX_LIGHTS          32
#define MAX_BOUNCES         64
#define SUB_RAYS            8
#define REFLECTION_COST     (1.0f / 3.0f)   /* 1 i% per 3 % of reflection */
#define BOX_MIN             (-12.0f)
#define BOX_MAX             ( 12.0f)

static QualityBands bands = {
    .darkness = 3.0f, .outline = 29.0f, .low_half = 45.0f,
    .low_norm = 65.0f, .good = 77.0f, .great = 89.0f,
    .best = 110.0f, .boost = 111.0f
};

/* ------------------------------------------------------------------ */
/*  Helpers                                                            */
/* ------------------------------------------------------------------ */

static float clampf(float v, float lo, float hi) {
    return v < lo ? lo : (v > hi ? hi : v);
}
static float len3(Vec3 v) { return sqrtf(v.x*v.x + v.y*v.y + v.z*v.z); }
static Vec3  sub3(Vec3 a, Vec3 b) { return (Vec3){a.x-b.x, a.y-b.y, a.z-b.z}; }
static Vec3  add3(Vec3 a, Vec3 b) { return (Vec3){a.x+b.x, a.y+b.y, a.z+b.z}; }
static Vec3  mul3(Vec3 a, float s) { return (Vec3){a.x*s, a.y*s, a.z*s}; }
static Vec3  norm3(Vec3 v) {
    float L = len3(v);
    return L > 1e-6f ? mul3(v, 1.0f/L) : (Vec3){0,1,0};
}
static float dist3(Vec3 a, Vec3 b) { return len3(sub3(a,b)); }

/* quality label for a given remaining i% */
static const char* quality_name(float i) {
    if (i <= bands.darkness) return "DARKNESS / NO LIGHT";
    if (i <= bands.outline)  return "OUTLINES & SILHOUETTES (1/4 dist)";
    if (i <= bands.low_half) return "LOW LIGHT (1/2 dist)";
    if (i <= bands.low_norm) return "LOW LIGHT (norm dist)";
    if (i <= bands.good)     return "GOOD LIGHT";
    if (i <= bands.great)    return "GREAT LIGHT";
    if (i <= bands.best)     return "BEST";
    return "BEST + DISTANCE BOOST";
}

/* ------------------------------------------------------------------ */
/*  8-sub-ray directional constraints (from the sketches)              */
/* ------------------------------------------------------------------ */

/* Returns a unit direction for sub-ray k (0..7).
 * Constraints taken from the notes:
 *   always dead-North, random-but-not-N-nor-E & opposite-of-E,
 *   always dead-South, random-opposite-side-but-not-South,
 *   make-cone, F→E, T→S, etc.
 */
static Vec3 sub_ray_dir(int k, Vec3 main_dir) {
    /* fixed cardinals first */
    static const Vec3 fixed[4] = {
        { 0,0,-1}, /* dead North */
        { 0,0, 1}, /* dead South */
        { 1,0, 0}, /* East  */
        {-1,0, 0}  /* West  */
    };
    if (k < 4) return fixed[k];

    /* remaining four are cone / random-but-constrained around main_dir */
    float angle = (k - 4) * (M_PI * 0.5f) + 0.35f;
    Vec3 side = { cosf(angle), 0.15f, sinf(angle) };
    /* reject pure North / pure East when the note says so */
    if (fabsf(side.z) > 0.92f && side.z < 0) side.z = -0.6f; /* not dead-N */
    if (fabsf(side.x) > 0.92f && side.x > 0) side.x =  0.6f; /* not pure-E */
    return norm3(add3(main_dir, side));
}

/* ------------------------------------------------------------------ */
/*  Degree-burst formula from the notes                                */
/*   ( (i%/3) - i% ) - AP   = degree burst                             */
/* ------------------------------------------------------------------ */

static float degree_burst(float i_pct, float ap_distance) {
    float reduced = i_pct / 3.0f;
    return (reduced - i_pct) - ap_distance;   /* negative = tighter cone */
}

/* ------------------------------------------------------------------ */
/*  Simple box-wall intersection (the “3-D space within a box”)        */
/* ------------------------------------------------------------------ */

static bool ray_box(Vec3 origin, Vec3 dir, float *t_hit, Vec3 *normal) {
    float tmin = 0.0f, tmax = 1e6f;
    Vec3 n = {0,0,0};
    const float bmin[3] = {BOX_MIN, 0.0f, BOX_MIN};
    const float bmax[3] = {BOX_MAX, 6.0f, BOX_MAX};
    const float o[3] = {origin.x, origin.y, origin.z};
    const float d[3] = {dir.x, dir.y, dir.z};

    for (int i = 0; i < 3; ++i) {
        if (fabsf(d[i]) < 1e-8f) {
            if (o[i] < bmin[i] || o[i] > bmax[i]) return false;
            continue;
        }
        float t1 = (bmin[i] - o[i]) / d[i];
        float t2 = (bmax[i] - o[i]) / d[i];
        float nsign = -1.0f;
        if (t1 > t2) { float tmp=t1; t1=t2; t2=tmp; nsign = 1.0f; }
        if (t1 > tmin) { tmin = t1; n = (Vec3){0,0,0}; ((float*)&n)[i] = nsign; }
        if (t2 < tmax) tmax = t2;
        if (tmin > tmax) return false;
    }
    *t_hit = tmin;
    *normal = n;
    return tmin >= 0.0f;
}

/* ------------------------------------------------------------------ */
/*  Core illuminosity tracer (unlimited bounces, cost per reflection)  */
/* ------------------------------------------------------------------ */

typedef struct {
    float remaining_i;        /* illuminosity left after all costs     */
    float travel;             /* total distance travelled              */
    int   bounces;
    Vec3  hit_pos;
} TraceResult;

static TraceResult trace_illuminance(const LightSource *src,
                                     const Aperture *ap,
                                     Vec3 sample_point,
                                     int max_bounces)
{
    TraceResult r = {0};
    Vec3 main_dir = norm3(sub3(src->target, src->pos));
    float ap_dist = ap ? ap->distance : 0.0f;
    float burst   = degree_burst(src->i_pct, ap_dist);

    /* start with the main “source ray” + 8 sub-rays */
    for (int ray = 0; ray < 1 + SUB_RAYS; ++ray) {
        Vec3 dir = (ray == 0) ? main_dir : sub_ray_dir(ray-1, main_dir);

        /* tighten cone according to degree burst (negative = narrower) */
        if (burst < 0.0f) {
            float tight = clampf(1.0f + burst * 0.01f, 0.15f, 1.0f);
            dir = norm3(add3(mul3(dir, tight), mul3(main_dir, 1.0f-tight)));
        }

        Vec3 origin = src->pos;
        float i_left = src->i_pct;
        float travelled = 0.0f;
        int bounces = 0;

        while (bounces < max_bounces && i_left > 0.01f) {
            float t;
            Vec3 n;
            if (!ray_box(origin, dir, &t, &n)) break;

            travelled += t;
            Vec3 hit = add3(origin, mul3(dir, t));

            /* cost of this reflection segment */
            float segment_cost = REFLECTION_COST * (t / src->radius) * 100.0f;
            i_left -= segment_cost;
            if (i_left <= 0.0f) break;

            /* did we reach the sample point? (within a small radius) */
            if (dist3(hit, sample_point) < 0.35f) {
                if (i_left > r.remaining_i) {
                    r.remaining_i = i_left;
                    r.travel      = travelled;
                    r.bounces     = bounces;
                    r.hit_pos     = hit;
                }
                break;
            }

            /* bounce: reflect and continue (unlimited inside radius) */
            float dn = dir.x*n.x + dir.y*n.y + dir.z*n.z;
            dir = sub3(dir, mul3(n, 2.0f * dn));
            dir = norm3(dir);
            origin = add3(hit, mul3(n, 0.01f)); /* bias */
            ++bounces;

            /* hard stop if we leave the illuminance sphere */
            if (travelled > src->radius * 1.5f) break;
        }
    }
    return r;
}

/* ------------------------------------------------------------------ */
/*  Day / night blend                                                  */
/* ------------------------------------------------------------------ */

static void daynight_update(DayNightCycle *dn, float dt) {
    if (!dn->playing || dn->paused) return;

    float period = (dn->time_of_day < 0.5f)
                 ? dn->day_to_night_s
                 : dn->night_to_day_s;
    dn->time_of_day += dt / (period * 2.0f); /* full cycle = day+night */
    if (dn->time_of_day >= 1.0f) dn->time_of_day -= 1.0f;
}

static void daynight_colors(const DayNightCycle *dn, Vec3 *out_col, float *out_i) {
    /* simple linear blend around dawn/dusk */
    float t = dn->time_of_day;
    float night_w;
    if (t < 0.25f)      night_w = 1.0f - t*4.0f;          /* midnight→dawn */
    else if (t < 0.75f) night_w = 0.0f;                   /* day           */
    else                night_w = (t-0.75f)*4.0f;         /* dusk→midnight */

    out_col->x = dn->day_color.x*(1-night_w) + dn->night_color.x*night_w;
    out_col->y = dn->day_color.y*(1-night_w) + dn->night_color.y*night_w;
    out_col->z = dn->day_color.z*(1-night_w) + dn->night_color.z*night_w;
    *out_i     = dn->day_i*(1-night_w) + dn->night_i*night_w;
}

/* ------------------------------------------------------------------ */
/*  Demo world                                                         */
/* ------------------------------------------------------------------ */

static LightSource lights[MAX_LIGHTS];
static int         n_lights = 0;
static Aperture    aperture = {
    .pos = {0,1.6f,0}, .distance = 2.5f,
    .color = {0.9f,0.85f,0.7f},
    .half_width = 1.2f, .bottom_y = 0.4f, .top_y = 2.8f
};
static DayNightCycle daynight = {
    .day_color   = {1.0f, 0.95f, 0.85f}, .day_i   = 95.0f,
    .night_color = {0.15f,0.18f,0.35f},  .night_i = 18.0f,
    .day_to_night_s = 45.0f, .night_to_day_s = 60.0f,
    .time_of_day = 0.35f, .playing = false, .paused = false
};

static void add_light(Vec3 pos, Vec3 target, float i, bool global, const char *name) {
    if (n_lights >= MAX_LIGHTS) return;
    LightSource *L = &lights[n_lights++];
    L->pos = pos; L->target = target; L->i_pct = i;
    L->radius = 9.0f; L->is_global = global; L->selected = false;
    L->color = global ? daynight.day_color : (Vec3){1.0f,0.9f,0.7f};
    strncpy(L->name, name, 31);
}

/* ------------------------------------------------------------------ */
/*  Side-panel dump (what the real UI would show)                      */
/* ------------------------------------------------------------------ */

static void print_side_panel(int active) {
    printf("\n========== SIDE PANEL ==========\n");
    if (active < 0 || active >= n_lights) {
        Vec3 gcol; float gi;
        daynight_colors(&daynight, &gcol, &gi);
        printf("  [GLOBAL LIGHT]  (no local source selected)\n");
        printf("  day   color (%.2f %.2f %.2f)  i%%=%.1f\n",
               daynight.day_color.x, daynight.day_color.y, daynight.day_color.z, daynight.day_i);
        printf("  night color (%.2f %.2f %.2f)  i%%=%.1f\n",
               daynight.night_color.x, daynight.night_color.y, daynight.night_color.z, daynight.night_i);
        printf("  current blend i%%=%.1f\n", gi);
        printf("  APERTURE (local)  dist=%.2f  color(%.2f %.2f %.2f)\n",
               aperture.distance, aperture.color.x, aperture.color.y, aperture.color.z);
    } else {
        LightSource *L = &lights[active];
        printf("  ACTIVE: %s  %s\n", L->name, L->is_global ? "(GLOBAL – cannot delete/region-select)" : "");
        printf("  pos (%.2f %.2f %.2f)  target (%.2f %.2f %.2f)\n",
               L->pos.x,L->pos.y,L->pos.z, L->target.x,L->target.y,L->target.z);
        printf("  radius=%.1f  i%%=%.1f  color(%.2f %.2f %.2f)\n",
               L->radius, L->i_pct, L->color.x,L->color.y,L->color.z);
        printf("  degree-burst = %.2f\n", degree_burst(L->i_pct, aperture.distance));
    }
    printf("  Day→Night scrollbar: %.0fs   Night→Day: %.0fs\n",
           daynight.day_to_night_s, daynight.night_to_day_s);
    printf("  Time-of-day: %.3f  [%s]\n",
           daynight.time_of_day,
           daynight.playing ? (daynight.paused ? "PAUSED" : "PLAYING") : "STOPPED");
    printf("================================\n");
}

/* ------------------------------------------------------------------ */
/*  Interactive state machine (maps directly onto SDL events)          */
/* ------------------------------------------------------------------ */

/*
 * LEFT-CLICK 1   → place new light source at clicked wall/floor/roof
 * LEFT-CLICK 2   → set its target (source ray)
 * LEFT-DRAG      → region-select (box) – globals are ignored
 * RIGHT-CLICK    → delete prompt for that light (globals refused)
 * RIGHT-DRAG     → multi-delete region
 * DOUBLE-RIGHT   → cancel selection
 * DOUBLE-LEFT    → move clicked point to centre of display
 *
 * The two bottom horizontal scrollbars control day↔night durations
 * (clamped 30–90 s).  Play / Pause / Stop buttons drive the cycle.
 */

typedef enum {
    MODE_IDLE,
    MODE_PLACE_SOURCE,   /* waiting for first left-click */
    MODE_PLACE_TARGET,   /* waiting for second left-click */
    MODE_REGION_SELECT,
    MODE_REGION_DELETE
} EditorMode;

static EditorMode mode = MODE_IDLE;
static int        active_light = -1;
static Vec3       pending_pos;

/* ------------------------------------------------------------------ */
/*  Main demo loop (console stand-in for the real GUI)                 */
/* ------------------------------------------------------------------ */

int main(void) {
    /* seed a global + two local lights so the lab is never empty */
    add_light((Vec3){0,5.5f,0}, (Vec3){0,0,0}, 110.0f, true,  "GlobalSky");
    add_light((Vec3){-6,2.2f,4}, (Vec3){0,1.5f,0}, 78.0f, false, "WallLamp_A");
    add_light((Vec3){ 5,1.8f,-3}, (Vec3){-2,1.0f,2}, 55.0f, false, "FloorSpot_B");

    printf("SignalCloud Illuminosity Lab  (from your handwritten notes)\n");
    printf("Box = [%.0f..%.0f] x [0..6] x [%.0f..%.0f]\n", BOX_MIN,BOX_MAX,BOX_MIN,BOX_MAX);
    printf("Commands (console stand-in for mouse):\n");
    printf("  a <x> <y> <z>     – add light source at point (then set target)\n");
    printf("  t <x> <y> <z>     – set target of pending / active light\n");
    printf("  s <index>         – select light (side panel updates)\n");
    printf("  d <index>         – delete light (globals refused)\n");
    printf("  p                 – play day/night\n");
    printf("  space             – pause / unpause\n");
    printf("  x                 – stop\n");
    printf("  l / r <seconds>   – set left/right scrollbar (30-90)\n");
    printf("  q                 – probe a sample point for quality\n");
    printf("  ?                 – list lights\n");
    printf("  quit\n\n");

    print_side_panel(active_light);

    char line[256];
    while (fgets(line, sizeof line, stdin)) {
        if (strncmp(line, "quit", 4) == 0) break;

        if (line[0] == 'a') {
            float x,y,z;
            if (sscanf(line+1, "%f %f %f", &x,&y,&z) == 3) {
                pending_pos = (Vec3){x,y,z};
                mode = MODE_PLACE_TARGET;
                printf("Source placed at (%.2f %.2f %.2f).  Now set target with 't x y z'\n", x,y,z);
            }
        }
        else if (line[0] == 't' && mode == MODE_PLACE_TARGET) {
            float x,y,z;
            if (sscanf(line+1, "%f %f %f", &x,&y,&z) == 3) {
                char name[32];
                snprintf(name, sizeof name, "Local_%d", n_lights);
                add_light(pending_pos, (Vec3){x,y,z}, 70.0f, false, name);
                active_light = n_lights - 1;
                mode = MODE_IDLE;
                printf("Light '%s' created.\n", name);
                print_side_panel(active_light);
            }
        }
        else if (line[0] == 's') {
            int idx;
            if (sscanf(line+1, "%d", &idx) == 1 && idx >= 0 && idx < n_lights) {
                active_light = idx;
                print_side_panel(active_light);
            }
        }
        else if (line[0] == 'd') {
            int idx;
            if (sscanf(line+1, "%d", &idx) == 1 && idx >= 0 && idx < n_lights) {
                if (lights[idx].is_global) {
                    printf("REFUSED: global lights cannot be deleted.\n");
                } else {
                    printf("Deleted '%s'\n", lights[idx].name);
                    memmove(&lights[idx], &lights[idx+1],
                            (n_lights-idx-1)*sizeof(LightSource));
                    --n_lights;
                    if (active_light == idx) active_light = -1;
                    else if (active_light > idx) --active_light;
                    print_side_panel(active_light);
                }
            }
        }
        else if (line[0] == 'p') {
            daynight.playing = true; daynight.paused = false;
            printf("Day/night PLAYING\n");
        }
        else if (line[0] == ' ') {
            daynight.paused = !daynight.paused;
            printf(daynight.paused ? "PAUSED\n" : "UNPAUSED\n");
        }
        else if (line[0] == 'x') {
            daynight.playing = false; daynight.paused = false;
            daynight.time_of_day = 0.35f;
            printf("STOPPED – time reset\n");
        }
        else if (line[0] == 'l') {
            float s;
            if (sscanf(line+1, "%f", &s) == 1)
                daynight.day_to_night_s = clampf(s, 30.0f, 90.0f);
            print_side_panel(active_light);
        }
        else if (line[0] == 'r') {
            float s;
            if (sscanf(line+1, "%f", &s) == 1)
                daynight.night_to_day_s = clampf(s, 30.0f, 90.0f);
            print_side_panel(active_light);
        }
        else if (line[0] == 'q') {
            float x,y,z;
            if (sscanf(line+1, "%f %f %f", &x,&y,&z) == 3) {
                Vec3 sample = {x,y,z};
                printf("\nProbe (%.2f %.2f %.2f):\n", x,y,z);
                for (int i = 0; i < n_lights; ++i) {
                    TraceResult tr = trace_illuminance(&lights[i], &aperture, sample, MAX_BOUNCES);
                    printf("  %-12s  remaining i%%=%.1f  travel=%.2f  bounces=%d  → %s\n",
                           lights[i].name, tr.remaining_i, tr.travel, tr.bounces,
                           quality_name(tr.remaining_i));
                }
            }
        }
        else if (line[0] == '?') {
            for (int i = 0; i < n_lights; ++i)
                printf("  [%d] %-12s  %s  i%%=%.0f\n",
                       i, lights[i].name,
                       lights[i].is_global ? "GLOBAL" : "local ",
                       lights[i].i_pct);
        }

        /* advance day/night a little each command so the cycle is visible */
        daynight_update(&daynight, 0.5f);
    }

    printf("Lab closed.\n");
    return 0;
}
