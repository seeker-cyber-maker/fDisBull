// Authored synthetic source backing; not recovered DinoPark code.
use std::env;

fn encode(s: &[u32; 5]) -> String {
    format!("{{\"cash\":\"{}\",\"working\":\"{}\",\"stock\":\"{}\",\"pending\":\"{}\",\"expense\":\"{}\"}}",
            s[0], s[1], s[2], s[3], s[4])
}

fn commit(mut s: [u32; 5], ready: bool) -> String {
    let mut checkpoints = Vec::new();
    if ready {
        s[2] = s[3];
        checkpoints.push(encode(&s));
        s[4] = s[4].wrapping_add(500);
        checkpoints.push(encode(&s));
        s[0] = s[1];
        checkpoints.push(encode(&s));
    }
    format!("{{\"status\":\"{}\",\"state\":{},\"events\":{},\"checkpoints\":[{}]}}",
            if ready { "complete" } else { "refused" }, encode(&s),
            if ready { "[\"stock\",\"expense\",\"cash\"]" } else { "[]" },
            checkpoints.join(","))
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    assert_eq!(args.len(), 6);
    let mut s = [0u32; 5];
    for i in 0..5 { s[i] = args[i].parse().expect("u32 operand"); }
    println!("{}", commit(s, args[5] == "1"));
}
