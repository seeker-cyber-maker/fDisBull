from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "src/fdisbull/game_sources/genesis_game_audio.c"


HARNESS = r"""
#include <stdio.h>
#include <stdint.h>

typedef unsigned char u8;
typedef unsigned short u16;
typedef unsigned long u32;

void audio_init(void);
void audio_request(u8 kind,u8 id);
void audio_tick(void);
u8 audio_busy(void);

static u8 streams[3][20];
static u16 status_word;
static unsigned calls;
static u8 operation[16];
static u32 first_arg[16],second_arg[16];
static u16 third_arg[16],fourth_arg[16];

const u8 *fdisbull_audio_test_stream(u8 kind,u8 id) {
    if (kind>=3 || id>=20) return 0;
    return &streams[kind][id];
}
void fdisbull_audio_test_record(u8 op,u32 a,u32 b,u16 c,u16 d) {
    operation[calls]=op;first_arg[calls]=a;second_arg[calls]=b;
    third_arg[calls]=c;fourth_arg[calls]=d;calls++;
}
u16 fdisbull_audio_test_status(void) { return status_word; }

int main(void) {
    audio_init();
    if (calls!=1 || operation[0]!=0) return 1;

    audio_request(1,1);
    if (calls!=2 || operation[1]!=1 ||
        first_arg[1]!=(u32)&streams[1][1] ||
        second_arg[1]!=(u32)0x554f4UL || third_arg[1]!=28) return 2;
    audio_request(1,13);
    if (calls!=3 || first_arg[2]!=(u32)&streams[1][13]) return 3;

    audio_request(2,1);
    if (calls!=4 || operation[3]!=2 ||
        first_arg[3]!=(u32)&streams[2][1] || third_arg[3]!=28 ||
        fourth_arg[3]!=0) return 4;
    audio_request(2,19);
    if (calls!=5 || fourth_arg[4]!=72 ||
        first_arg[4]!=(u32)&streams[2][19]) return 5;

    audio_request(0,1);
    audio_request(1,0);
    audio_request(1,14);
    audio_request(2,0);
    audio_request(2,20);
    if (calls!=5) return 6;

    audio_request(3,0);
    audio_request(1,255);
    if (calls!=7 || operation[5]!=3 || operation[6]!=3) return 7;

    status_word=0;
    if (audio_busy()!=0) return 8;
    status_word=(u16)(1U<<5);
    if (audio_busy()!=1) return 9;
    status_word=(u16)((1U<<4)|(1U<<0));
    if (audio_busy()!=0) return 10;

    audio_tick();
    if (calls!=7) return 11;
    puts("genesis audio selector contract passed");
    return 0;
}
"""


def test_genesis_audio_request_mapping(tmp_path: Path) -> None:
    compiler = shutil.which("cc") or shutil.which("clang") or shutil.which("gcc")
    if compiler is None:
        pytest.skip("a host C compiler is required for the Genesis audio adapter test")
    harness = tmp_path / "audio_harness.c"
    binary = tmp_path / "audio_harness"
    harness.write_text(HARNESS)
    subprocess.run(
        [
            compiler,
            "-std=c99",
            "-O2",
            "-Wall",
            "-Wextra",
            "-DFDISBULL_GENESIS_AUDIO_HOST",
            str(SOURCE),
            str(harness),
            "-o",
            str(binary),
        ],
        check=True,
        capture_output=True,
        text=True,
    )
    result = subprocess.run([str(binary)], check=True, capture_output=True, text=True)
    assert "selector contract passed" in result.stdout
