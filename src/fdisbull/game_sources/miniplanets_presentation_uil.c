/* Authored executable presentation model for the checked Miniplanets NES
 * adapter. Game UIL authoring notation; no original cartridge bytes. */
typedef unsigned char u8;
typedef unsigned short u16;
u8 presentation_plane[256];
u8 presentation_palettes[256];
u8 presentation_staging[296];
u8 presentation_shadow0[296];
u8 presentation_shadow1[296];
u8 presentation_nt_valid[2];
u8 presentation_last_overlay[2];
u8 presentation_active_nt;
u8 presentation_ready;
u8 presentation_target_nt;
u8 presentation_count;
u8 presentation_cursor;
u8 presentation_jobs[22];
u8 presentation_chunk_end[22];
u8 presentation_terrain_cached;
u8 presentation_terrain_valid;
u8 presentation_overlay;
u8 presentation_sparse;
u8 presentation_sparse_valid;
u8 presentation_staging_valid;
u8 presentation_force;
u8 presentation_reuse;
u8 presentation_chunk_start;
u16 presentation_budget;
/* The checked projection union, ordered as native jobs 22..35. */
const u8 presentation_span_offset[14]={5,18,34,50,65,81,97,113,129,145,161,178,194,212};
const u8 presentation_span_length[14]={7,12,12,13,14,14,14,14,14,14,14,12,12,8};
/* Cells painted by all 256 checked projection pages. */
const u8 presentation_painted_start[14]={7,4,3,2,2,2,1,1,2,2,2,3,4,6};
const u8 presentation_painted_length[14]={2,8,10,12,12,13,14,14,13,12,12,10,8,4};

/* Main-thread decision, not an independent renderer. Call only with a
 * completed input-state snapshot. A pending upload rejects classification. */
u8 presentation_classify(u8 mode,u8 ending,u8 status) {
    if (presentation_ready!=0) return 0;
    presentation_terrain_cached=0;
    presentation_sparse=0;
    presentation_overlay=status & 1;
    if (mode==1 && ending!=3 && (status & 1)==0) presentation_sparse=1;
    return 1;
}

/* The painter subsequently overwrites the interior. Bytes excluded from the
 * partial clear are meaningful only under the checked projection profile. */
u8 presentation_clear_terrain(void) {
    u16 i;
    u8 row;
    u8 column;
    if (presentation_ready!=0) return 0;
    presentation_staging_valid=0;
    for(i=0;i<256;i=i+1) {
        row=(u8)(i>>4);column=(u8)(i & 15);
        if (row>=14 || column<presentation_painted_start[row] ||
            column>=presentation_painted_start[row]+presentation_painted_length[row]) {
            presentation_plane[i]=0;presentation_palettes[i]=0;
        }
    }
    return 1;
}

/* A terrain miss invalidates both exact-view certificates before repaint. */
u8 presentation_terrain_miss(void) {
    if (presentation_ready!=0) return 0;
    presentation_terrain_cached=0;
    presentation_terrain_valid=0;
    presentation_clear_terrain();
    return 1;
}

/* Individual IDs correspond to 16 full rows, two HUD jobs, four attribute
 * jobs and fourteen compact terrain spans, in that order. */
void presentation_region(u8 id,u16 offset,u8 length) {
    u8 i;
    u8 dirty;
    u16 at;
    u16 charge;
    if(presentation_ready!=0) return;
    dirty=presentation_force;
    for(i=0;i<length;i=i+1) {
        at=offset+i;
        if(presentation_target_nt==0) {
            if(presentation_staging[at]!=presentation_shadow0[at]) dirty=1;
        } else {
            if(presentation_staging[at]!=presentation_shadow1[at]) dirty=1;
        }
    }
    if(dirty==0) return;
    charge=(u16)(46+(u16)length*8);
    if(charge>presentation_budget) {
        presentation_chunk_end[presentation_chunk_start]=presentation_count;
        presentation_chunk_start=presentation_count;
        presentation_budget=1218;
    }
    presentation_budget=presentation_budget-charge;
    presentation_jobs[presentation_count]=id;
    presentation_count=presentation_count+1;
    for(i=0;i<length;i=i+1) {
        at=offset+i;
        if(presentation_target_nt==0) presentation_shadow0[at]=presentation_staging[at];
        else presentation_shadow1[at]=presentation_staging[at];
    }
}

/* Speculative shadows become reusable only after all chunks commit. The
 * calling protocol keeps staging, plan and hints immutable while ready=1. */
u8 presentation_prepare(void) {
    u8 mask;
    u8 i;
    u8 compact;
    if(presentation_ready!=0) return 0;
    presentation_count=0;presentation_cursor=0;presentation_chunk_start=0;
    presentation_budget=1218;
    presentation_target_nt=presentation_active_nt ^ 1;
    presentation_force=presentation_nt_valid[presentation_target_nt] ^ 1;
    mask=1;
    if(presentation_target_nt!=0) mask=2;
    presentation_reuse=0;
    if(presentation_terrain_cached!=0 && presentation_force==0 &&
       (presentation_terrain_valid & mask)!=0 &&
       presentation_overlay==presentation_last_overlay[presentation_target_nt]) presentation_reuse=1;
    if(presentation_reuse==0) {
        compact=0;
        if(presentation_sparse!=0 && presentation_force==0 &&
           (presentation_sparse_valid & mask)!=0) compact=1;
        if(compact!=0) {
            for(i=0;i<14;i=i+1) presentation_region((u8)(22+i),presentation_span_offset[i],presentation_span_length[i]);
        } else {
            for(i=0;i<16;i=i+1) presentation_region(i,(u16)i*16,16);
        }
    }
    presentation_region(16,256,12);presentation_region(17,268,12);
    if(presentation_reuse==0) {
        for(i=0;i<4;i=i+1) presentation_region((u8)(18+i),(u16)(280+(u16)i*4),4);
    }
    if(presentation_terrain_cached!=0) {
        presentation_terrain_valid=presentation_terrain_valid | mask;
        presentation_last_overlay[presentation_target_nt]=presentation_overlay;
    } else presentation_terrain_valid=presentation_terrain_valid & (u8)~mask;
    if(presentation_sparse!=0) presentation_sparse_valid=presentation_sparse_valid | mask;
    else presentation_sparse_valid=presentation_sparse_valid & (u8)~mask;
    presentation_chunk_end[presentation_chunk_start]=presentation_count;
    presentation_nt_valid[presentation_target_nt]=1;
    presentation_ready=1;
    return 1;
}

/* One bounded NMI chunk; callers apply corresponding queued writes before
 * invoking the next chunk. Return 1 only at the final coherent commit. */
u8 presentation_complete(void) {
    if(presentation_ready==0) return 255;
    if(presentation_cursor<presentation_count)
        presentation_cursor=presentation_chunk_end[presentation_cursor];
    if(presentation_cursor==presentation_count) {
        presentation_active_nt=presentation_target_nt;
        presentation_ready=0;
        return 1;
    }
    return 0;
}
