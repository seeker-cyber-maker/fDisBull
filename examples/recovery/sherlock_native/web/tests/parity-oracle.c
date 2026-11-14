/* Authored finite C -> JavaScript comparison oracle. This executes the existing
 * native implementation; it does not emulate or newly qualify original DOS.
 * JSONL output contains authored puzzles and test observations only. */
#include "../../core/sherlock_logic.h"
#include "../../state/sherlock_state.h"
#include "../../state/sherlock_hint_proof.h"
#include <assert.h>
#include <inttypes.h>
#include <limits.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define ANSWER(a) ((const uint8_t (*)[6])(a))
#define MASKS(a) ((const uint8_t (*)[6])(a))

static void string(const char *s) {
    putchar('"');
    for (; *s; ++s) {
        unsigned char c = (unsigned char)*s;
        if (c == '"' || c == '\\') { putchar('\\'); putchar(c); }
        else if (c == '\n') fputs("\\n", stdout);
        else if (c == '\r') fputs("\\r", stdout);
        else if (c == '\t') fputs("\\t", stdout);
        else if (c < 32) printf("\\u%04x", c);
        else putchar(c);
    }
    putchar('"');
}
static void u8matrix(const uint8_t a[6][6]) {
    unsigned r, c;
    putchar('[');
    for (r = 0; r < 6; ++r) {
        if (r) putchar(',');
        putchar('[');
        for (c = 0; c < 6; ++c) { if (c) putchar(','); printf("%u", a[r][c]); }
        putchar(']');
    }
    putchar(']');
}
static void i8matrix(const int8_t a[6][6]) {
    unsigned r, c;
    putchar('[');
    for (r = 0; r < 6; ++r) {
        if (r) putchar(',');
        putchar('[');
        for (c = 0; c < 6; ++c) { if (c) putchar(','); printf("%d", a[r][c]); }
        putchar(']');
    }
    putchar(']');
}
static void clue(const SherlockClue *c) {
    printf("{\"type\":%u,\"a\":%u,\"b\":%u,\"c\":%u}", c->type,c->a,c->b,c->c);
}
static void puzzle(const SherlockPuzzle *p) {
    unsigned i;
    printf("{\"number\":%u,\"given\":", p->number); i8matrix(p->given);
    printf(",\"solution\":"); u8matrix(p->solution);
    printf(",\"clue_count\":%u,\"clues\":[",p->clue_count);
    for (i=0;i<p->clue_count;++i) { if(i)putchar(',');clue(&p->clues[i]); }
    fputs("],\"original_slot\":[",stdout);
    for (i=0;i<p->clue_count;++i) { if(i)putchar(',');printf("%u",p->original_slot[i]); }
    fputs("]}",stdout);
}
static void hint(const SHHint *h) {
    printf("{\"kind\":%d,\"row\":%u,\"column\":%u,\"item\":%u,\"clue_index\":%d,\"explanation\":",
        h->kind,h->row,h->column,h->item,h->clue_index);
    string(h->explanation);putchar('}');
}
static void state(const SherlockGame *g) {
    unsigned b,k,s,r,c; uint8_t cells[6][6];
    fputs("{\"board\":{\"candidates\":",stdout);u8matrix(g->board.candidates);
    fputs(",\"chosen\":",stdout);i8matrix(g->board.chosen);
    fputs(",\"clue_slots\":[",stdout);
    for(b=0;b<2;++b) {
        if(b)putchar(',');
        putchar('[');
        for(k=0;k<2;++k) {
            if(k)putchar(',');
            putchar('[');
            for(s=0;s<(k?21u:18u);++s) {if(s)putchar(',');printf("%d",g->board.clue_slots[b][k][s]);}
            putchar(']');
        }
        putchar(']');
    }
    fputs("]},\"fixed\":",stdout);u8matrix(g->fixed);
    for(r=0;r<6;++r)for(c=0;c<6;++c)cells[r][c]=sh_cell_byte(g,r,c);
    fputs(",\"cell_bytes\":",stdout);u8matrix(ANSWER(cells));
    printf(",\"undo_count\":%u,\"outcome\":%d,\"elapsed_ms\":\"%" PRIu64 "\",\"limit_ms\":\"%" PRIu64
        "\",\"display_time_ms\":\"%" PRIu64 "\",\"paused\":%d,\"hint_pending\":%d,\"pending_hint\":",
        g->undo_count,g->outcome,g->elapsed_ms,g->limit_ms,sh_display_time_ms(g),g->paused,g->hint_pending);
    if(g->pending_hint.kind)hint(&g->pending_hint);else fputs("null",stdout);
    putchar('}');
}
static SherlockPuzzle blank(void) {
    SherlockPuzzle p;memset(&p,0,sizeof p);memset(p.given,-1,sizeof p.given);
    memset(p.solution,255,sizeof p.solution);memset(p.original_slot,255,sizeof p.original_slot);return p;
}
static void identity(uint8_t a[6][6]) {
    unsigned r,c;for(r=0;r<6;++r)for(c=0;c<6;++c)a[r][c]=(uint8_t)c;
}
static void fix_identity(SherlockPuzzle *p) {
    unsigned r,c;for(r=0;r<6;++r)for(c=0;c<6;++c)p->given[r][c]=(int8_t)c;
}
static void start(const char *kind,const char *name) {
    fputs("{\"kind\":",stdout);string(kind);fputs(",\"case\":",stdout);string(name);
}
static void verify_case(const char *name,const SherlockPuzzle *p,const uint8_t a[6][6]) {
    SherlockVerifyResult result;sherlock_verify_answer(p,a,&result);
    start("verify",name);fputs(",\"puzzle\":",stdout);puzzle(p);fputs(",\"answer\":",stdout);u8matrix(a);
    printf(",\"expected\":{\"status\":%d,\"row\":%d,\"column\":%d,\"clue_index\":%d}}\n",
        result.status,result.row,result.column,result.clue_index);
}
static void solve_case(const char *name,const SherlockPuzzle *p,uint64_t budget) {
    SherlockSolveResult result;sherlock_analyze(p,budget,&result);
    start("analyze",name);fputs(",\"puzzle\":",stdout);puzzle(p);
    printf(",\"budget\":\"%" PRIu64 "\",\"expected\":{\"status\":%d,\"solution_count\":%u,\"nodes\":\"%" PRIu64 "\",\"first_solution\":",
        budget,result.status,result.solution_count,result.nodes);u8matrix(ANSWER(result.first_solution));
    fputs(",\"second_solution\":",stdout);u8matrix(ANSWER(result.second_solution));fputs("}}\n",stdout);
}
static void generator_case(const char *name,uint64_t seed,const SherlockGenerateLimits *limits) {
    SherlockPuzzle p;SherlockGenerateResult result;
    SherlockGenerateStatus status=sherlock_generate_random(seed,limits,&p,&result);
    start("generate",name);printf(",\"seed\":\"%" PRIu64 "\",\"limits\":",seed);
    if(limits)printf("{\"node_budget\":\"%" PRIu64 "\",\"max_attempts\":%u,\"max_givens\":%u}",limits->node_budget,limits->max_attempts,limits->max_givens);
    else fputs("null",stdout);
    printf(",\"expected\":{\"status\":%d,\"report\":{\"status\":%d,\"seed\":\"%" PRIu64 "\",\"version\":%u,\"attempts\":%u,\"nodes\":\"%" PRIu64 "\",\"clue_count\":%u,\"given_count\":%u,\"proof\":%d},\"puzzle\":",
        status,result.status,result.seed,result.version,result.attempts,result.nodes,result.clue_count,result.given_count,result.proof);
    if(status==SH_GENERATE_OK)puzzle(&p);else fputs("null",stdout);
    fputs("}}\n",stdout);
}
static void candidate_case(const char *name,const SherlockGame *g,unsigned budget) {
    unsigned remaining=budget;
    int status=sh_check_candidates(&g->puzzle,g->board.candidates,&remaining);
    start("candidates",name);fputs(",\"puzzle\":",stdout);puzzle(&g->puzzle);
    fputs(",\"candidates\":",stdout);u8matrix(g->board.candidates);
    printf(",\"budget\":%u,\"expected\":{\"status\":%d,\"remaining_nodes\":%u,\"nodes_used\":%u}}\n",
        budget,status,remaining,budget-remaining);
}
static void hint_case(const char *name,const SherlockGame *g,unsigned bank,unsigned budget) {
    SHHint h;int ret=sh_find_hint_in_bank(g,bank,&h,budget);
    start("hint",name);fputs(",\"puzzle\":",stdout);puzzle(&g->puzzle);fputs(",\"state\":",stdout);state(g);
    printf(",\"bank\":%u,\"budget\":%u,\"expected\":{\"result\":%d,\"hint\":",bank,budget,ret);hint(&h);fputs("}}\n",stdout);
}
static void proof_record(const SHHintProof *p) {
    unsigned i;
    printf("{\"version\":%u,\"background_rules\":%u,\"target\":{\"kind\":%d,\"row\":%u,\"column\":%u,\"item\":%u},\"selected_clue_index\":%d,\"candidates\":",
        p->version,p->background_rules,p->target.kind,p->target.row,p->target.column,p->target.item,p->selected_clue_index);
    u8matrix(p->candidates);fputs(",\"given\":",stdout);i8matrix(p->given);
    printf(",\"source_clue_count\":%u,\"support_count\":%u,\"support\":[",p->source_clue_count,p->support_count);
    for(i=0;i<p->support_count;++i) {
        if(i)putchar(',');
        printf("{\"index\":%u,\"clue\":",p->support[i].index);clue(&p->support[i].clue);putchar('}');
    }
    fputs("]}",stdout);
}
static void proof_report(const SHHintProofResult *r) {
    printf("{\"status\":%d,\"node_budget\":%u,\"nodes_used\":%u,\"deletion_checks\":%u,\"reduction_complete\":%d}",
        r->status,r->node_budget,r->nodes_used,r->deletion_checks,r->reduction_complete);
}
static void proof_case(const char *name,const SherlockGame *g,const SHHint *h,unsigned budget) {
    SHHintProof p;SHHintProofResult report;
    int result=sh_explain_hint(g,h,budget,&p,&report);
    start("proof",name);fputs(",\"puzzle\":",stdout);puzzle(&g->puzzle);fputs(",\"state\":",stdout);state(g);
    fputs(",\"selected\":",stdout);hint(h);printf(",\"budget\":%u,\"expected\":{\"status\":%d,\"record\":",budget,result);
    proof_record(&p);fputs(",\"report\":",stdout);proof_report(&report);fputs("}}\n",stdout);
}
static void replay_case(const char *name,const SHHintProof *p,unsigned budget) {
    SHHintProofResult report;int result=sh_replay_hint_proof(p,budget,&report);
    start("replay",name);fputs(",\"record\":",stdout);proof_record(p);
    printf(",\"budget\":%u,\"expected\":{\"status\":%d,\"report\":",budget,result);proof_report(&report);fputs("}}\n",stdout);
}
static SHHint selected(enum SHHintKind kind,unsigned r,unsigned c,unsigned item,int index) {
    SHHint h;memset(&h,0,sizeof h);h.kind=kind;h.row=(uint8_t)r;h.column=(uint8_t)c;h.item=(uint8_t)item;h.clue_index=(int16_t)index;return h;
}
static void small_game(SherlockGame *g) {
    SherlockPuzzle p=blank();unsigned r,c;sh_game_init(g,&p,0);
    for(r=0;r<6;++r)for(c=0;c<6;++c)g->board.candidates[r][c]=(uint8_t)(1u<<c);
}
static void combined_game(SherlockGame *g) {
    unsigned r,c;small_game(g);
    for(r=0;r<2;++r)for(c=0;c<3;++c)g->board.candidates[r][c]=7;
    g->puzzle.clue_count=4;
    g->puzzle.clues[0]=(SherlockClue){SHERLOCK_LEFT_OF,0,6,255};
    g->puzzle.clues[1]=(SherlockClue){SHERLOCK_SAME_COLUMN,6,13,255};
    g->puzzle.clues[2]=(SherlockClue){SHERLOCK_LEFT_OF,18,29,255};
    g->puzzle.clues[3]=(SherlockClue){SHERLOCK_UNUSED,35,255,255};
}

static int first_step;
static void begin_trace(const char *name,const SherlockPuzzle *p,unsigned limit,SherlockGame *g) {
    sh_game_init(g,p,limit);start("trace",name);fputs(",\"puzzle\":",stdout);puzzle(p);
    printf(",\"limit_seconds\":%u,\"initial\":",limit);state(g);fputs(",\"steps\":[",stdout);first_step=1;
}
static void step(SherlockGame *g,const char *op,unsigned a,unsigned b,unsigned c,uint64_t n) {
    int result=0,is_void=0;unsigned count=0;unsigned args[3]={a,b,c};
    if(!first_step)putchar(',');
    first_step=0;
    if(!strcmp(op,"remove")){count=3;result=sh_remove(g,a,b,c);}
    else if(!strcmp(op,"restore")){count=3;result=sh_restore(g,a,b,c);}
    else if(!strcmp(op,"choose")){count=3;result=sh_choose(g,a,b,c);}
    else if(!strcmp(op,"undo"))result=sh_undo(g);
    else if(!strcmp(op,"archiveClue")){count=1;result=sh_archive_clue(g,a);}
    else if(!strcmp(op,"moveClue")){count=2;result=sh_move_clue(g,a,b);}
    else if(!strcmp(op,"setPaused")){count=1;is_void=1;sh_set_paused(g,(int)a);}
    else if(!strcmp(op,"tick")){is_void=1;sh_tick(g,n);}
    else if(!strcmp(op,"quit")){is_void=1;sh_quit(g);}
    else if(!strcmp(op,"requestHint")){count=2;result=sh_request_hint_in_bank(g,a,b);}
    else if(!strcmp(op,"acceptHint"))result=sh_accept_hint(g);
    else {fprintf(stderr,"Unknown oracle operation %s\n",op);exit(3);}
    fputs("{\"op\":",stdout);string(op);fputs(",\"args\":[",stdout);
    if(!strcmp(op,"tick"))printf("\"%" PRIu64 "\"",n);
    else for(unsigned i=0;i<count;++i){if(i)putchar(',');printf("%u",args[i]);}
    fputs("],\"return\":",stdout);if(is_void)fputs("null",stdout);else printf("%d",result);
    fputs(",\"state\":",stdout);state(g);putchar('}');
}
static void end_trace(void){fputs("]}\n",stdout);}

int main(void) {
    SherlockPuzzle p;SherlockGame g;SHHint h;SHHintProof record,changed;SHHintProofResult pr;
    uint8_t answer[6][6];unsigned t,a,b,c,i,r;char name[96];
    static const uint64_t seeds[]={0,1,2,42,235,65535,UINT64_C(4294967295),UINT64_C(4294967296),UINT64_C(9007199254740991),UINT64_C(9007199254740992),UINT64_C(9223372036854775808),UINT64_MAX};
    static const SherlockClue true_clues[]={
        {0,0,6,255},{1,0,7,255},{2,0,7,255},{3,0,8,255},{4,0,7,255},{5,0,7,14},{6,0,9,14},{7,0,255,255}};
    static const SherlockClue false_clues[]={
        {0,0,7,255},{1,0,6,255},{2,0,8,255},{3,0,7,255},{4,1,6,255},{5,0,8,14},{6,0,7,14}};
    start("relations","all-eight-predicates");fputs(",\"values\":[",stdout);
    for(t=0;t<8;++t)for(a=0;a<6;++a)for(b=0;b<6;++b)for(c=0;c<6;++c){
        if(t||a||b||c)putchar(',');
        printf("%d",sherlock_relation_holds(t,(int)a,(int)b,(int)c));
    }fputs("]}\n",stdout);
    p=blank();identity(answer);verify_case("empty-permutation-accepted",&p,ANSWER(answer));
    answer[0][0]=1;answer[0][1]=0;verify_case("alternative-permutation-accepted",&p,ANSWER(answer));
    p.given[0][0]=0;verify_case("given-mismatch",&p,ANSWER(answer));p.given[0][0]=-1;
    identity(answer);answer[2][3]=2;verify_case("duplicate-row-item",&p,ANSWER(answer));
    answer[2][3]=255;verify_case("out-of-range-item",&p,ANSWER(answer));identity(answer);
    for(t=0;t<8;++t){p.clue_count=1;p.clues[0]=true_clues[t];snprintf(name,sizeof name,"relation-%u-accepted",t);verify_case(name,&p,ANSWER(answer));
        if(t<7){p.clues[0]=false_clues[t];snprintf(name,sizeof name,"relation-%u-rejected",t);verify_case(name,&p,ANSWER(answer));}}
    p=blank();solve_case("empty-zero-budget",&p,0);solve_case("empty-one-node",&p,1);solve_case("empty-multiple",&p,100);
    fix_identity(&p);solve_case("fully-given-unique",&p,1);p.given[5][0]=p.given[5][1]=-1;
    solve_case("two-permutations-budget-one",&p,1);solve_case("two-permutations-budget-two",&p,2);solve_case("two-permutations-decided",&p,100);
    p.given[5][1]=0;p.given[5][0]=0;solve_case("contradictory-givens",&p,100);
    p=blank();p.clue_count=1;p.clues[0]=(SherlockClue){SHERLOCK_NOT_SAME_COLUMN,0,0,255};solve_case("repeated-object-contradiction",&p,100);
    p.clues[0]=(SherlockClue){SHERLOCK_NEXT_TO,0,0,255};solve_case("self-neighbor-contradiction",&p,100);
    p.clues[0]=(SherlockClue){SHERLOCK_LEFT_OF,0,0,255};solve_case("self-left-contradiction",&p,100);
    p.clues[0]=(SherlockClue){SHERLOCK_SAME_COLUMN,0,1,255};solve_case("same-row-distinct-same-column",&p,100);
    p=blank();p.given[1][1]=6;solve_case("invalid-given",&p,100);
    for(i=0;i<sizeof seeds/sizeof seeds[0];++i){snprintf(name,sizeof name,"seed-%" PRIu64,seeds[i]);generator_case(name,seeds[i],NULL);}
    {SherlockGenerateLimits lim={0,16,3};generator_case("generation-zero-budget",42,&lim);lim.node_budget=1;generator_case("generation-one-node",42,&lim);
        lim.node_budget=1000000;lim.max_attempts=0;generator_case("generation-zero-attempts",42,&lim);lim.max_attempts=65;generator_case("generation-invalid-attempts",42,&lim);
        lim.max_attempts=16;lim.max_givens=4;generator_case("generation-invalid-givens",42,&lim);}
    small_game(&g);candidate_case("singleton-masks-zero-budget",&g,0);candidate_case("singleton-masks-sat",&g,1);
    g.board.candidates[0][0]=0;candidate_case("empty-mask-unsat",&g,1);g.board.candidates[0][0]=64;candidate_case("mask-high-bit-invalid",&g,10);
    small_game(&g);g.puzzle.given[0][0]=1;candidate_case("given-enforced-separately",&g,10);
    small_game(&g);g.puzzle.given[0][0]=6;candidate_case("given-range-invalid",&g,10);
    p=blank();sh_game_init(&g,&p,0);candidate_case("full-masks-low-budget",&g,1);candidate_case("full-masks-sat",&g,100);
    hint_case("unconstrained-no-search",&g,0,0);hint_case("unconstrained-budget-one",&g,0,1);
    small_game(&g);hint_case("singleton-select",&g,0,20000);g.board.candidates[0][0]=0;hint_case("empty-cell-contradiction",&g,0,20000);
    for(t=0;t<7;++t){p=blank();p.clue_count=1;p.clues[0]=true_clues[t];p.original_slot[0]=(uint8_t)(t<2?36:54);sh_game_init(&g,&p,0);
        (void)sh_choose(&g,0,0,0);snprintf(name,sizeof name,"clue-family-%u",t);hint_case(name,&g,0,20000);}
    p=blank();p.clue_count=2;p.clues[0]=(SherlockClue){0,0,6,255};p.clues[1]=(SherlockClue){0,1,7,255};p.original_slot[0]=36;p.original_slot[1]=37;
    sh_game_init(&g,&p,0);sh_remove(&g,0,0,0);sh_remove(&g,0,1,1);hint_case("first-visible-clue",&g,0,20000);sh_archive_clue(&g,0);
    hint_case("other-visible-clue-after-archive",&g,0,20000);hint_case("archived-bank-hint",&g,1,20000);
    combined_game(&g);h=selected(SH_HINT_REMOVE,0,1,0,0);
    {static const unsigned budgets[]={0,1,2,3,4,5,6,8,16,1000};for(i=0;i<sizeof budgets/sizeof budgets[0];++i){snprintf(name,sizeof name,"combined-proof-budget-%u",budgets[i]);proof_case(name,&g,&h,budgets[i]);}}
    assert(sh_explain_hint(&g,&h,1000,&record,&pr)==SH_PROOF_PROVED);
    replay_case("valid-support",&record,1000);replay_case("replay-zero-budget",&record,0);replay_case("replay-one-node",&record,1);
    changed=record;changed.version=2;replay_case("wrong-proof-version",&changed,1000);
    changed=record;changed.background_rules=0;replay_case("missing-row-rule",&changed,1000);
    changed=record;changed.candidates[0][0]=64;replay_case("invalid-replay-mask",&changed,1000);
    changed=record;changed.target.kind=SH_HINT_NONE;replay_case("invalid-target-kind",&changed,1000);
    changed=record;changed.support[1].index=changed.support[0].index;replay_case("duplicate-support-index",&changed,1000);
    changed=record;changed.support[0].index=changed.source_clue_count;replay_case("support-index-outside-source",&changed,1000);
    changed=record;changed.support[0].clue.type=SHERLOCK_UNUSED;replay_case("inactive-card-as-support",&changed,1000);
    changed=record;changed.target.column=0;replay_case("fixed-target-changed-to-refuted",&changed,1000);
    h=selected(SH_HINT_CHOOSE,0,0,0,0);proof_case("combined-choose",&g,&h,1000);
    h=selected(SH_HINT_REMOVE,0,0,0,0);proof_case("proposed-removal-refuted",&g,&h,1000);
    h=selected(SH_HINT_CHOOSE,0,2,2,0);proof_case("unforced-choice-refuted",&g,&h,1000);
    h=selected(SH_HINT_REMOVE,0,1,0,0);g.board.candidates[5][5]=0;proof_case("inconsistent-is-not-proof",&g,&h,1000);
    combined_game(&g);h=selected(SH_HINT_REMOVE,0,1,5,0);proof_case("absent-target-invalid",&g,&h,1000);
    small_game(&g);g.board.candidates[0][0]=g.board.candidates[0][1]=15;g.board.candidates[0][2]=g.board.candidates[0][3]=12;
    g.board.candidates[0][4]=g.board.candidates[0][5]=48;h=selected(SH_HINT_REMOVE,0,0,2,-1);proof_case("hall-set-no-clues",&g,&h,1000);
    small_game(&g);g.board.candidates[0][0]=g.board.candidates[0][1]=3;g.puzzle.given[0][0]=0;h=selected(SH_HINT_CHOOSE,0,0,0,-1);proof_case("given-background-separate",&g,&h,1000);
    small_game(&g);g.board.candidates[1][0]=g.board.candidates[1][1]=3;g.puzzle.clue_count=3;
    g.puzzle.clues[0]=(SherlockClue){0,0,6,255};g.puzzle.clues[1]=(SherlockClue){0,0,12,255};g.puzzle.clues[2]=(SherlockClue){0,12,6,255};
    h=selected(SH_HINT_CHOOSE,1,0,0,0);proof_case("prefer-direct-selected-clue",&g,&h,1000);
    small_game(&g);g.board.candidates[1][0]=g.board.candidates[1][1]=3;g.puzzle.clue_count=256;
    for(i=0;i<255;++i)g.puzzle.clues[i]=(SherlockClue){7,0,255,255};
    g.puzzle.clues[255]=(SherlockClue){0,0,6,255};
    h=selected(SH_HINT_CHOOSE,1,0,0,255);proof_case("source-index-255",&g,&h,1000);

    p=blank();p.given[0][5]=5;p.clue_count=5;
    p.clues[0]=(SherlockClue){0,0,6,255};p.original_slot[0]=36;
    p.clues[1]=(SherlockClue){1,1,8,255};p.original_slot[1]=39;
    p.clues[2]=(SherlockClue){4,2,10,255};p.original_slot[2]=54;
    p.clues[3]=(SherlockClue){3,3,11,255};p.original_slot[3]=60;
    p.clues[4]=(SherlockClue){7,5,255,255};p.original_slot[4]=74;
    begin_trace("edits-layout-pause",&p,0,&g);
    step(&g,"remove",0,5,5,0);step(&g,"restore",0,0,0,0);step(&g,"remove",1,2,4,0);step(&g,"remove",1,2,4,0);step(&g,"restore",1,2,4,0);
    step(&g,"choose",2,4,3,0);step(&g,"choose",2,0,3,0);step(&g,"remove",2,4,3,0);step(&g,"restore",2,4,3,0);step(&g,"choose",2,4,3,0);
    step(&g,"setPaused",1,0,0,0);step(&g,"remove",0,0,0,0);step(&g,"archiveClue",0,0,0,0);step(&g,"tick",0,0,0,1234);
    step(&g,"setPaused",0,0,0,0);step(&g,"tick",0,0,0,1000);step(&g,"archiveClue",0,0,0,0);step(&g,"moveClue",0,5,0,0);step(&g,"archiveClue",0,0,0,0);
    step(&g,"moveClue",1,17,0,0);step(&g,"moveClue",2,20,0,0);step(&g,"moveClue",4,0,0,0);
    step(&g,"moveClue",0,18,0,0);step(&g,"moveClue",2,21,0,0);step(&g,"archiveClue",999,0,0,0);step(&g,"remove",6,0,0,0);step(&g,"choose",0,0,6,0);
    for(i=0;i<20;++i)step(&g,"undo",0,0,0,0);
    end_trace();
    p=blank();begin_trace("undo-limit-25",&p,0,&g);
    for(i=0;i<60;++i)step(&g,i%2?"restore":"remove",0,0,0,0);
    for(i=0;i<27;++i)step(&g,"undo",0,0,0,0);
    end_trace();
    p=blank();p.clue_count=39;
    for(i=0;i<39;++i){p.clues[i]=(SherlockClue){7,(uint8_t)(i%36),255,255};p.original_slot[i]=(uint8_t)(36+i);}
    begin_trace("full-clue-grid-insertion",&p,0,&g);step(&g,"moveClue",0,17,0,0);step(&g,"moveClue",17,0,0,0);step(&g,"moveClue",18,20,0,0);step(&g,"moveClue",38,0,0,0);
    step(&g,"archiveClue",0,0,0,0);step(&g,"archiveClue",17,0,0,0);step(&g,"archiveClue",0,0,0,0);step(&g,"undo",0,0,0,0);end_trace();
    p=blank();p.clue_count=1;p.clues[0]=(SherlockClue){4,0,6,255};p.original_slot[0]=54;
    begin_trace("deferred-hint-timeout",&p,20,&g);step(&g,"tick",0,0,0,19000);step(&g,"requestHint",0,20000,0,0);step(&g,"tick",0,0,0,25000);
    step(&g,"remove",0,0,0,0);step(&g,"archiveClue",0,0,0,0);step(&g,"requestHint",1,20000,0,0);step(&g,"acceptHint",0,0,0,0);step(&g,"undo",0,0,0,0);step(&g,"tick",0,0,0,10);end_trace();
    for(i=0;i<2;++i){p=blank();fix_identity(&p);p.given[5][5]=-1;
        begin_trace(i?"final-hint-at-deadline":"final-hint-before-deadline",&p,60,&g);step(&g,"tick",0,0,0,i?29999:29998);step(&g,"requestHint",0,20000,0,0);
        step(&g,"tick",0,0,0,1);step(&g,"acceptHint",0,0,0,0);step(&g,"undo",0,0,0,0);end_trace();}
    p=blank();begin_trace("clock-saturation-and-quit",&p,0,&g);step(&g,"tick",0,0,0,UINT64_MAX-10);step(&g,"tick",0,0,0,30);step(&g,"setPaused",1,0,0,0);step(&g,"tick",0,0,0,100);
    step(&g,"setPaused",0,0,0,0);step(&g,"quit",0,0,0,0);step(&g,"tick",0,0,0,1);step(&g,"choose",0,0,0,0);end_trace();
    p=blank();p.clue_count=1;p.clues[0]=(SherlockClue){0,0,7,255};p.original_slot[0]=36;
    begin_trace("complete-wrong-answer",&p,0,&g);for(r=0;r<6;++r)for(c=0;c<6;++c)step(&g,"choose",r,c,c,0);step(&g,"undo",0,0,0,0);end_trace();
    for(i=0;i<3;++i){SherlockGenerateResult gr;uint64_t seed=i==0?0:i==1?42:UINT64_MAX;
        assert(sherlock_generate_random(seed,NULL,&p,&gr)==SH_GENERATE_OK);snprintf(name,sizeof name,"complete-hint-game-%" PRIu64,seed);begin_trace(name,&p,0,&g);
        for(t=0;t<260&&g.outcome==SH_PLAYING;++t){int found=sh_find_hint(&g,&h,20000);assert(found==1);step(&g,"requestHint",0,20000,0,0);step(&g,"acceptHint",0,0,0,0);}
        assert(g.outcome==SH_WON);end_trace();}
    return ferror(stdout)?2:0;
}
