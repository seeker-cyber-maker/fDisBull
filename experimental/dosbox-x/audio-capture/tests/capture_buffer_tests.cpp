#include "agent/audio_capture.h"
#include <cassert>
#include <iostream>
using namespace dosbox_agent;
int main() {
    AudioCaptureBuffer b; AudioCaptureSnapshot s; std::string error;
    const std::int16_t samples[] = {-32768,32767,-1,0,0x1234,-0x1234,12,13};
    for (auto size : {0u,1u,3u,5u,4194308u}) assert(!b.Start("A",size,44100,7,100,&error));
    assert(!b.Start("",12,44100,7,100,&error)); assert(!b.Start("A",12,0,7,100,&error));
    assert(b.Start("A",12,44100,7,100,&error)); const auto first=b.CurrentId();
    assert(!b.Start("A",12,44100,7,100,&error) && error=="CAPTURE_ACTIVE");
    assert(b.Get("A",first,false,8,&s,&error) && s.active && s.pcm.empty() && !s.complete);
    assert(!b.Get("B",first,false,8,&s,&error)); assert(!b.Get("A",first+1,false,8,&s,&error));
    b.Append(44100,3,samples,9,100);
    assert(b.Get("A",first,false,9,&s,&error));
    assert(!s.active && s.complete && s.truncated && s.stop_reason=="byte_limit" && s.byte_count==12 && s.pcm.empty());
    assert(s.first_mixer_frame==100 && s.next_mixer_frame==103 && s.captured_frames==3);
    assert(b.Get("A",first,true,999,&s,&error));
    assert(s.pcm==std::vector<std::uint8_t>({0,128,255,127,255,255,0,0,52,18,204,237}));
    assert(s.end_guest_ticks==9); b.Append(44100,1,samples,1000,103);
    assert(b.Get("A",first,true,1001,&s,&error) && s.byte_count==12 && s.end_guest_ticks==9);
    assert(b.Start("A",12,22050,200,500,&error)); const auto second=b.CurrentId(); assert(second>first);
    b.Append(22050,4,samples,201,500);
    assert(b.Get("A",second,true,202,&s,&error) && s.byte_count==12 && s.next_mixer_frame==503 && s.truncated);
    assert(!b.Get("A",first,true,203,&s,&error));
    assert(b.Start("A",16,44100,300,600,&error)); auto id=b.CurrentId(); b.Append(44100,2,samples,301,600);
    assert(b.Get("A",id,true,302,&s,&error) && s.complete && !s.truncated && s.stop_reason=="requested" && s.byte_count==8 && s.next_mixer_frame==602);
    assert(b.Start("A",16,44100,400,700,&error)); id=b.CurrentId(); b.EndOwner("B",401,"state_load");assert(b.Active());
    b.EndOwner("A",402,"state_load");assert(b.Get("A",id,true,403,&s,&error) && s.truncated && s.stop_reason=="state_load");
    b.Reset();assert(!b.Get("A",id,true,404,&s,&error));
    assert(b.Start("A",16,44100,500,800,&error));id=b.CurrentId();b.Append(22050,1,samples,501,800);
    assert(b.Get("A",id,true,502,&s,&error) && s.byte_count==0 && s.sample_rate==44100 && s.stop_reason=="format_changed");
    assert(b.Start("A",16,44100,600,900,&error));id=b.CurrentId();b.Append(44100,1,samples,599,900);
    assert(b.Get("A",id,true,601,&s,&error) && s.byte_count==0 && s.stop_reason=="timeline_discontinuity");
    assert(b.Start("A",16,44100,700,1000,&error));id=b.CurrentId();b.Append(44100,1,samples,701,1001);
    assert(b.Get("A",id,true,702,&s,&error) && s.byte_count==0 && s.stop_reason=="timeline_discontinuity");
    assert(b.Start("A",4194304,44100,800,1100,&error));id=b.CurrentId();assert(b.Get("A",id,true,801,&s,&error) && s.max_bytes==4194304 && !s.truncated);
    std::cout << "bounded PCM capture contract passed\n";
}
