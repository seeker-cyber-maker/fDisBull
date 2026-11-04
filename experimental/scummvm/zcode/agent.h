// SPDX-License-Identifier: GPL-3.0-or-later
// Opt-in headless control for the actual ScummVM GLK/ZCode interpreter.
// This file contains transport/control logic, never Z-machine opcode semantics.
#ifndef FDISBULL_ZCODE_AGENT_H
#define FDISBULL_ZCODE_AGENT_H
#include <algorithm>
#include <cerrno>
#include <chrono>
#include <cstdint>
#include <cstdlib>
#include <deque>
#include <map>
#include <string>
#include <vector>
#include <poll.h>
#include <sys/socket.h>
#include <unistd.h>

namespace FDisBullZCode {
using Number = std::int64_t;
using Clock = std::chrono::steady_clock;
static constexpr Number MAX_ID = 9007199254740991LL;

inline std::string quote(const std::string &s) {
    static const char digits[] = "0123456789abcdef";
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += char(c); }
        else if (c < 32) { out += "\\u00"; out += digits[c >> 4]; out += digits[c & 15]; }
        else out += char(c);
    }
    return out + '"';
}
inline std::string number(Number n) { return std::to_string(n); }
inline std::string hex(const std::uint8_t *p, size_t count) {
    static const char d[] = "0123456789abcdef";
    std::string out; out.reserve(count * 2);
    for (size_t i = 0; i < count; ++i) { out += d[p[i] >> 4]; out += d[p[i] & 15]; }
    return out;
}

// The inherited-socket protocol uses flat requests. Reject nested values,
// duplicate fields, floats, malformed escapes and unbounded integers rather
// than coercing them. Unicode text input is deliberately outside v3 profile.
struct Value {
    enum Kind { Integer, String, Boolean, Null } kind = Null;
    Number n = 0;
    std::string s;
};
using Request = std::map<std::string, Value>;
class Parser {
    const std::string &_s; size_t _p = 0;
    void ws() { while (_p < _s.size() && (_s[_p]==' ' || _s[_p]=='\t' || _s[_p]=='\r')) ++_p; }
    bool take(char c) { ws(); if (_p == _s.size() || _s[_p] != c) return false; ++_p; return true; }
    bool literal(const char *s) {
        size_t end = _p; while (*s) { if (end >= _s.size() || _s[end++] != *s++) return false; }
        _p = end; return true;
    }
    bool string(std::string &out) {
        if (!take('"')) return false;
        out.clear();
        while (_p < _s.size()) {
            unsigned char c = _s[_p++];
            if (c == '"') return true;
            if (c < 32 || c > 126) return false;
            if (c == '\\') {
                if (_p == _s.size()) return false;
                c = _s[_p++];
                switch (c) {
                case '"': case '\\': case '/': break;
                case 'n': c='\n'; break; case 'r': c='\r'; break;
                case 't': c='\t'; break; case 'b': c='\b'; break; case 'f': c='\f'; break;
                case 'u': {
                    unsigned v = 0;
                    for (int i=0; i<4; ++i) {
                        if (_p == _s.size()) return false;
                        char h=_s[_p++]; int d=h>='0'&&h<='9'?h-'0':h>='a'&&h<='f'?h-'a'+10:h>='A'&&h<='F'?h-'A'+10:-1;
                        if (d<0) return false;
                        v=(v<<4)|unsigned(d);
                    }
                    if (v>127) return false;
                    c=static_cast<unsigned char>(v); break;
                }
                default: return false;
                }
            }
            out += char(c);
        }
        return false;
    }
public:
    explicit Parser(const std::string &s): _s(s) {}
    bool parse(Request &out) {
        out.clear(); if (!take('{')) return false;
        ws(); if (take('}')) { ws(); return _p==_s.size(); }
        for (int fields=0; fields<32; ++fields) {
            std::string key; if (!string(key) || key.empty() || key.size()>64 || !take(':') || out.count(key)) return false;
            ws(); if (_p==_s.size()) return false;
            Value v;
            if (_s[_p]=='"') { v.kind=Value::String; if (!string(v.s)) return false; }
            else if (literal("true")) { v.kind=Value::Boolean; v.n=1; }
            else if (literal("false")) { v.kind=Value::Boolean; }
            else if (literal("null")) { v.kind=Value::Null; }
            else {
                v.kind=Value::Integer; bool neg=false;
                if (_s[_p]=='-') { neg=true; if (++_p==_s.size()) return false; }
                if (_s[_p]<'0' || _s[_p]>'9') return false;
                bool zero=_s[_p]=='0'; int digits=0;
                while (_p<_s.size() && _s[_p]>='0' && _s[_p]<='9') {
                    if (zero && digits) return false;
                    unsigned d=unsigned(_s[_p++]-'0'); ++digits;
                    if (v.n>(MAX_ID-d)/10) return false;
                    v.n=v.n*10+d;
                }
                if (neg) v.n=-v.n;
            }
            out.emplace(key,v); ws();
            if (take('}')) { ws(); return _p==_s.size(); }
            if (!take(',')) return false;
        }
        return false;
    }
};
inline Number integer(const Request &r,const char *key,Number fallback=-1) {
    auto i=r.find(key); return i!=r.end() && i->second.kind==Value::Integer ? i->second.n : fallback;
}
inline std::string text(const Request &r,const char *key) {
    auto i=r.find(key); return i!=r.end() && i->second.kind==Value::String ? i->second.s : std::string();
}

class Agent {
    struct Point { Number pc; std::string guard; };
    struct Span { Number id, parent, pc; };
    int _fd=-1;
    std::string _rx;
    std::uint8_t *_memory=nullptr;
    size_t _size=0;
    std::vector<std::uint8_t> _source;
    bool _running=false, _fault=false, _pause=false, _inputReady=false;
    Number _revision=0, _pc=0, _completed=0, _runStart=0, _limit=0, _runId=-1;
    Number _nextSpan=1, _nextPoint=1, _nextInput=1, _requestId=0;
    std::string _phase="boot", _inputKind, _input;
    size_t _inputMax=0;
    Clock::time_point _deadline;
    std::vector<Span> _spans;
    std::map<Number,Point> _points;
    std::deque<std::string> _trace, _output;
    size_t _outputBytes=0;
    Number _traceDropped=0;
    Span _position{0,0,0};
    static constexpr size_t TRACE_CAP=2048, OUTPUT_CAP=1024*1024;

    [[noreturn]] static void lostOwner(int code) { ::_exit(code); }
    void send(Number id, const std::string &fields, bool ok=true) {
        std::string s="{\"id\":"+number(id)+",\"ok\":"+(ok?"true":"false")+fields+"}\n";
        if (s.size()>8*1024*1024) lostOwner(75);
        size_t p=0; const auto deadline=Clock::now()+std::chrono::seconds(5);
        while (p<s.size()) {
            auto ms=std::chrono::duration_cast<std::chrono::milliseconds>(deadline-Clock::now()).count();
            if (ms<=0) lostOwner(75);
            pollfd fd{_fd,POLLOUT,0};
            int ready=::poll(&fd,1,static_cast<int>(ms));
            if (ready<0 && errno==EINTR) continue;
            if (ready<=0 || (fd.revents&(POLLERR|POLLHUP|POLLNVAL))) lostOwner(75);
            ssize_t n=::send(_fd,s.data()+p,s.size()-p,MSG_DONTWAIT
#ifdef MSG_NOSIGNAL
                |MSG_NOSIGNAL
#endif
            );
            if (n<0 && (errno==EINTR || errno==EAGAIN || errno==EWOULDBLOCK)) continue;
            if (n<=0) lostOwner(75);
            p+=static_cast<size_t>(n);
        }
    }
    void error(Number id,const char *message) { send(id,",\"error\":\"refused\",\"message\":"+quote(message),false); }
    bool line(bool block,std::string &out) {
        for (;;) {
            auto p=_rx.find('\n');
            if (p!=std::string::npos) { out=_rx.substr(0,p); _rx.erase(0,p+1); return true; }
            pollfd fd{_fd,POLLIN,0}; int ready=::poll(&fd,1,block?-1:0);
            if (ready<0 && errno==EINTR) continue;
            if (ready<0) lostOwner(74);
            if (!ready) return false;
            char data[4096]; ssize_t n=::recv(_fd,data,sizeof(data),0);
            if (n<0 && errno==EINTR) continue;
            if (n<=0) lostOwner(n==0?0:74);
            _rx.append(data,static_cast<size_t>(n));
            if (_rx.size()>65536) lostOwner(74);
        }
    }
    std::string position() const {
        return "{\"pc\":"+number(_position.pc)+",\"span_id\":"+number(_position.id)+
            ",\"parent_span_id\":"+number(_position.parent)+"}";
    }
    std::string state() const {
        return "{\"paused\":"+std::string(_running?"false":"true")+",\"phase\":"+quote(_phase)+
            ",\"revision\":"+number(_revision)+",\"pc\":"+number(_pc)+
            ",\"position\":"+position()+",\"completed_dispatches\":"+number(_completed)+
            ",\"input_request\":"+number(_requestId)+",\"input_kind\":"+quote(_inputKind)+
            ",\"input_max\":"+number(_inputMax)+",\"input_queued\":"+std::string(_inputReady?"true":"false")+
            ",\"faulted\":"+std::string(_fault?"true":"false")+"}";
    }
    void finish(const std::string &reason) {
        _running=false;
        if (_runId<0) return;
        const Number id=_runId; _runId=-1;
        send(id,",\"stop\":{\"reason\":"+quote(reason)+",\"paused\":true,\"phase\":"+quote(_phase)+
            ",\"pc\":"+number(_pc)+",\"revision\":"+number(_revision)+
            ",\"completed_dispatches\":"+number(_completed-_runStart)+",\"position\":"+position()+"}");
    }
    void record(const char *kind) {
        if (_trace.size()==TRACE_CAP) { _trace.pop_front(); ++_traceDropped; }
        _trace.push_back("{\"kind\":"+quote(kind)+",\"position\":"+position()+
                         ",\"revision\":"+number(_revision)+"}");
    }
    void handle(const std::string &s) {
        Request r;
        if (!Parser(s).parse(r)) { error(-1,"Malformed or non-flat JSON request"); lostOwner(74); }
        Number id=integer(r,"id"); const std::string op=text(r,"op");
        if (id<1 || op.empty()) { error(-1,"Request needs positive id and op"); lostOwner(74); }
        if (op=="quit") { send(id,",\"closed\":true"); lostOwner(0); }
        if (op=="pause") { _pause=_running; send(id,",\"acknowledged\":true,\"confirmed_stopped\":"+std::string(_running?"false":"true")); return; }
        if (_running) { error(id,"Pause and confirm stop before another operation"); return; }
        if (op=="hello") {
            send(id,",\"protocol\":\"fdisbull-scummvm-agent\",\"protocol_version\":1,\"bridge_version\":1,"
                 "\"engine\":\"glk\",\"subengine\":\"zcode\",\"profile\":\"glk-zcode-v3\",\"zversion\":3,"
                 "\"source_size\":"+number(_source.size())+",\"source_binding\":\"readback-required\","
                 "\"original_x86_executed\":false,\"virtual_clock\":false,\"paused\":true,"
                 "\"capabilities\":[\"state.get\",\"source.read\",\"memory.read\",\"run\",\"step\",\"pause\","
                 "\"break.add\",\"break.remove\",\"input\",\"text.get\",\"trace.get\",\"trace.clear\",\"quit\"]");
        } else if (op=="state.get") { send(id,",\"state\":"+state()); }
        else if (op=="source.read" || op=="memory.read") {
            Number at=integer(r,"offset"), n=integer(r,"length"), rev=integer(r,"revision");
            if (at<0 || n<1 || n>4096 || at>Number(_size) || n>Number(_size)-at || rev!=_revision) { error(id,"Invalid/stale memory range"); return; }
            const auto *p=op=="source.read"?_source.data():_memory;
            send(id,",\"offset\":"+number(at)+",\"length\":"+number(n)+",\"revision\":"+number(rev)+
                    ",\"hex\":"+quote(hex(p+at,static_cast<size_t>(n))));
        } else if (op=="run" || op=="step") {
            Number count=op=="step"?1:integer(r,"max_instructions"), ms=integer(r,"max_ms");
            if (_fault || _phase=="exited" || count<1 || count>1000000 || ms<1 || ms>600000) { error(id,"Faulted/exited session or invalid finite budget"); return; }
            _runId=id; _runStart=_completed; _limit=count; _pause=false;
            _deadline=Clock::now()+std::chrono::milliseconds(ms);
            if (_phase=="input_pending" && !_inputReady) { finish("input_pending"); return; }
            _running=true;
        } else if (op=="input") {
            std::string value=text(r,"text");
            auto field=r.find("text");
            if (_phase!="input_pending" || _inputReady || integer(r,"request")!=_requestId || integer(r,"revision")!=_revision ||
                field==r.end() || field->second.kind!=Value::String || value.size()>_inputMax ||
                (_inputKind=="char" && value.size()!=1) ||
                std::any_of(value.begin(),value.end(),[](unsigned char c){return c<32 || c>126;})) {
                error(id,"Input must match current request/revision and ASCII capacity"); return;
            }
            _input=value; _inputReady=true; ++_revision;
            send(id,",\"queued\":true,\"consumed\":false,\"revision\":"+number(_revision)+",\"request\":"+number(_requestId));
        } else if (op=="break.add") {
            Number pc=integer(r,"pc"); std::string guard=text(r,"expected_hex");
            if (pc<64 || pc>=Number(_size) || guard.empty() || guard.size()%2 || guard.size()>32 ||
                pc+Number(guard.size()/2)>Number(_size) || guard!=hex(_memory+pc,guard.size()/2) || _points.size()>=256) {
                error(id,"Invalid breakpoint range/guard or capacity"); return;
            }
            Number point=_nextPoint++; _points.emplace(point,Point{pc,guard});
            send(id,",\"breakpoint_id\":"+number(point)+",\"pc\":"+number(pc));
        } else if (op=="break.remove") {
            Number point=integer(r,"breakpoint_id");
            if (!_points.erase(point)) { error(id,"Unknown breakpoint"); return; }
            send(id,",\"removed\":true");
        } else if (op=="trace.clear") { _trace.clear(); _traceDropped=0; send(id,""); }
        else if (op=="trace.get") {
            std::string a; for (const auto &e:_trace) { if(!a.empty()) a+=','; a+=e; }
            send(id,",\"events\":["+a+"],\"dropped\":"+number(_traceDropped));
        } else if (op=="text.get") {
            std::string a; for (const auto &e:_output) { if(!a.empty()) a+=','; a+=e; }
            send(id,",\"events\":["+a+"],\"revision\":"+number(_revision));
            _output.clear(); _outputBytes=0;
        } else error(id,"Unsupported Z-code operation");
    }
    void control(const char *forced=nullptr) {
        std::string s;
        // Bounded drain prevents owner traffic starving an execution budget.
        for(int i=0;i<32 && line(false,s);++i) handle(s);
        if (_running) {
            if (forced) finish(forced);
            else if (_pause) finish("pause");
            else if (_completed-_runStart>=_limit) finish("budget");
            else if (Clock::now()>=_deadline) finish("host_timeout");
        }
        while (!_running) { if (line(true,s)) handle(s); }
    }
public:
    Agent() {
        const char *value=std::getenv("FDISBULL_SCUMMVM_FD");
        if (!value || !*value) return;
        char *end=nullptr; errno=0; long fd=std::strtol(value,&end,10);
        if (errno || !end || *end || fd<3 || fd>1048575) lostOwner(74);
        _fd=static_cast<int>(fd);
#ifdef SO_NOSIGPIPE
        int one=1; if (::setsockopt(_fd,SOL_SOCKET,SO_NOSIGPIPE,&one,sizeof(one))<0) lostOwner(74);
#endif
    }
    bool enabled() const { return _fd>=0; }
    void loaded(std::uint8_t *memory,size_t size) {
        if (!enabled()) return;
        if (!memory || size<64 || size>131072 || memory[0]!=3 || !_source.empty()) lostOwner(76);
        _memory=memory; _size=size; _source.assign(memory,memory+size);
    }
    Number before(Number pc) {
        if (!enabled()) return 0;
        if (!_memory || pc<64 || pc>=Number(_size) || _spans.size()>=128 || _nextSpan>=MAX_ID) lostOwner(76);
        Span span{_nextSpan++,_spans.empty()?0:_spans.back().id,pc};
        _spans.push_back(span); _position=span; _pc=pc; _phase="before_opcode"; ++_revision;
        record("before");
        const char *reason=nullptr;
        for (const auto &p:_points) if (p.second.pc==pc) {
            if (p.second.guard!=hex(_memory+pc,p.second.guard.size()/2)) { _fault=true; reason="code_changed"; }
            else reason="breakpoint";
            break;
        }
        if (_memory[pc]==0xb5 || _memory[pc]==0xb6) {
            _fault=true; reason="unsupported_save_restore";
        }
        control(reason);
        return span.id;
    }
    void after(Number span,Number nextPC) {
        if (!enabled()) return;
        if (_spans.empty() || _spans.back().id!=span) lostOwner(76);
        _position=_spans.back(); _spans.pop_back(); _pc=nextPC;
        _phase="after_opcode"; ++_revision; ++_completed; record("after"); control();
    }
    void exited(Number pc) {
        if (!enabled()) return;
        _pc=pc; _phase="exited"; ++_revision; finish("quit");
        std::string s; for (;;) if(line(true,s)) handle(s);
    }
    std::string input(const char *kind,size_t max,int timeout,int continued=0) {
        if (!_memory || max>4096 || timeout || continued) lostOwner(76);
        _phase="input_pending"; _inputKind=kind; _inputMax=max; _requestId=_nextInput++;
        _inputReady=false; ++_revision;
        control("input_pending");
        if (!_inputReady) lostOwner(76);
        std::string value=_input; _input.clear(); _inputReady=false;
        _requestId=0; _inputKind.clear(); _phase="inside_opcode"; ++_revision;
        return value;
    }
    void character(std::uint32_t c,int window) {
        if (!enabled()) return;
        if (c==13) c=10;
        if (c>0x10ffff || (c>=0xd800 && c<=0xdfff)) lostOwner(76);
        std::string utf;
        if(c<0x80) utf+=char(c);
        else if(c<0x800) { utf+=char(0xc0|(c>>6)); utf+=char(0x80|(c&63)); }
        else if(c<0x10000) { utf+=char(0xe0|(c>>12)); utf+=char(0x80|((c>>6)&63)); utf+=char(0x80|(c&63)); }
        else { utf+=char(0xf0|(c>>18)); utf+=char(0x80|((c>>12)&63)); utf+=char(0x80|((c>>6)&63)); utf+=char(0x80|(c&63)); }
        // Small contiguous chunks keep JSON event overhead bounded.
        std::string e="{\"window\":"+number(window)+",\"text\":"+quote(utf)+"}";
        if (_outputBytes+e.size()>OUTPUT_CAP || _output.size()>=16384) lostOwner(77);
        _outputBytes+=e.size(); _output.push_back(e);
    }
};
inline Agent &agent() { static Agent instance; return instance; }
} // namespace FDisBullZCode
#endif
