"""Cache the key points of each earnings call (structured JSON) so later analysis reads the summary, not the transcript.

Input : turns Parquet from build.py (local workdir, or downloaded from bucket market-data)
Output: Supabase table transcript_summaries (db/migrations/2026-11-25_transcript_summaries.sql)
        + a local JSONL copy under <workdir>/summaries/

usage:
  python summarize.py pilot <workdir> --n 30 --models claude-opus-5-5,claude-haiku-5-5   # synchronous, local JSONL only
  python summarize.py submit <workdir> --model claude-opus-5-5 [--years 2015,2016] [--limit N]
  python summarize.py collect <workdir> <batch_id>        # poll, then upsert results into transcript_summaries
Needs ANTHROPIC_API_KEY in the environment.
"""
import argparse, json, os, random, sys, time

import anthropic
import duckdb
from anthropic.types.message_create_params import MessageCreateParamsNonStreaming
from anthropic.types.messages.batch_create_params import Request

PROMPT_VERSION = "v1"
MAX_INPUT_CHARS = 600_000  # ~150k tokens; longer calls are rare and are flagged, not truncated silently

SYSTEM = """You read one company's earnings-call transcript and extract what a buy-side analyst would want cached,
so the transcript need not be re-read. Work only from the transcript; do not add outside knowledge or hindsight.

- key_points: the 6-12 most important statements by management, each attributed to the speaker's role
  (CEO, CFO, other). Prefer the CEO's own views: strategy, demand, outlook, risks, capital allocation, and what
  they say is changing. Each point is one self-contained sentence with numbers where given. `quote` is a short
  verbatim excerpt (<= 30 words) that supports the point.
- guidance: forward-looking numbers or directional outlook, as stated.
- analyst_focus: what analysts pressed on in Q&A, and how management answered (one line each).
- topics: 3-10 short lowercase tags for the themes discussed (e.g. "strong dollar", "china demand", "ai capex",
  "pricing", "buybacks", "tariffs", "interest rates", "m&a", "cost cuts", "drug pricing").
- ceo_present: whether the CEO speaks on the call. If not, still summarize the other executives.
- tone: management's overall tone about the business outlook.
Write in English. Be concrete; skip boilerplate (safe harbor, thank-yous, operator instructions)."""

POINT = {
    "type": "object",
    "properties": {
        "speaker_role": {"type": "string", "enum": ["CEO", "CFO", "other_executive"]},
        "speaker": {"type": "string"},
        "point": {"type": "string"},
        "topic": {"type": "string"},
        "stance": {"type": "string", "enum": ["positive", "negative", "neutral", "mixed"]},
        "quote": {"type": "string"},
    },
    "required": ["speaker_role", "speaker", "point", "topic", "stance", "quote"],
    "additionalProperties": False,
}
SCHEMA = {
    "type": "object",
    "properties": {
        "one_line": {"type": "string"},
        "ceo_present": {"type": "boolean"},
        "tone": {"type": "string", "enum": ["very positive", "positive", "neutral", "cautious", "negative"]},
        "key_points": {"type": "array", "items": POINT},
        "guidance": {"type": "array", "items": {"type": "string"}},
        "analyst_focus": {"type": "array", "items": {"type": "string"}},
        "topics": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["one_line", "ceo_present", "tone", "key_points", "guidance", "analyst_focus", "topics"],
    "additionalProperties": False,
}


def load_calls(W, years=None):
    con = duckdb.connect()
    cond = f"where substr(call_date,1,4) in ({','.join(repr(str(y)) for y in years)})" if years else ""
    rows = con.execute(f"""select symbol, call_date, turn, speaker, role, section, title, is_ceo, text
        from read_parquet('{W}/out/turns/*.parquet') {cond} order by symbol, call_date, turn""").fetchall()
    calls = {}
    for s, d, i, sp, role, sec, title, ceo, text in rows:
        calls.setdefault((s, d), []).append((sp, role, sec, title, ceo, text))
    return calls


def render(symbol, date, turns):
    lines = [f"Company: {symbol}   Call date: {date}"]
    for sp, role, sec, title, ceo, text in turns:
        if role == "operator" or not text.strip():
            continue
        tag = "CEO" if ceo else role
        who = f"{sp} ({title})" if title else sp
        lines.append(f"[{sec} | {tag}] {who}: {text.strip()}")
    body = "\n\n".join(lines)
    return body[:MAX_INPUT_CHARS], len(body) > MAX_INPUT_CHARS


def params(model, symbol, date, turns):
    body, cut = render(symbol, date, turns)
    if cut:
        print(f"warning: {symbol} {date} longer than {MAX_INPUT_CHARS} chars, truncated", file=sys.stderr)
    return dict(
        model=model,
        max_tokens=16000,
        system=[{"type": "text", "text": SYSTEM, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": body}],
        output_config={"effort": "medium", "format": {"type": "json_schema", "schema": SCHEMA}},
    )


def parse_message(msg):
    if msg.stop_reason == "refusal":
        return None, "refusal"
    if msg.stop_reason == "max_tokens":
        return None, "max_tokens"
    text = next((b.text for b in msg.content if b.type == "text"), None)
    return (json.loads(text), None) if text else (None, "no_text")


def row(symbol, date, model, summary, usage):
    return {"symbol": symbol, "call_date": date, "prompt_version": PROMPT_VERSION, "model": model,
            "summary": summary, "input_tokens": usage.input_tokens, "output_tokens": usage.output_tokens}


def cmd_pilot(a):
    client = anthropic.Anthropic()
    calls = load_calls(a.workdir)
    random.seed(7)
    keys = random.sample(sorted(calls), a.n)
    os.makedirs(f"{a.workdir}/summaries", exist_ok=True)
    out = open(f"{a.workdir}/summaries/pilot_{PROMPT_VERSION}.jsonl", "a")
    for model in a.models.split(","):
        tin = tout = 0
        for s, d in keys:
            try:
                msg = client.messages.create(**params(model, s, d, calls[(s, d)]))
            except anthropic.BadRequestError as e:
                print(f"{model} {s} {d}: bad request {e.message}"); continue
            except anthropic.APIStatusError as e:
                print(f"{model} {s} {d}: API error {e.status_code}"); continue
            summ, err = parse_message(msg)
            tin += msg.usage.input_tokens + (msg.usage.cache_read_input_tokens or 0); tout += msg.usage.output_tokens
            out.write(json.dumps({**row(s, d, model, summ, msg.usage), "error": err}) + "\n"); out.flush()
            print(model, s, d, err or "ok", msg.usage.input_tokens, msg.usage.output_tokens, flush=True)
        print(f"== {model}: {len(keys)} calls, input {tin} tok, output {tout} tok", flush=True)


def cmd_submit(a):
    client = anthropic.Anthropic()
    years = [int(y) for y in a.years.split(",")] if a.years else None
    calls = load_calls(a.workdir, years)
    keys = sorted(calls)[: a.limit] if a.limit else sorted(calls)
    reqs = [Request(custom_id=f"{s}|{d}", params=MessageCreateParamsNonStreaming(**params(a.model, s, d, calls[(s, d)])))
            for s, d in keys]
    ids = []
    for i in range(0, len(reqs), 2000):  # stay well under the 256 MB per-batch limit
        b = client.messages.batches.create(requests=reqs[i:i + 2000])
        ids.append(b.id); print("batch", b.id, len(reqs[i:i + 2000]), flush=True)
    os.makedirs(f"{a.workdir}/summaries", exist_ok=True)
    with open(f"{a.workdir}/summaries/batches.jsonl", "a") as f:
        for i in ids:
            f.write(json.dumps({"batch_id": i, "model": a.model, "prompt_version": PROMPT_VERSION}) + "\n")


def cmd_collect(a):
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
    from seekingalpha_quant.data import supabase_db as db
    client = anthropic.Anthropic()
    while (b := client.messages.batches.retrieve(a.batch_id)).processing_status != "ended":
        print("status", b.processing_status, b.request_counts.processing, flush=True); time.sleep(60)
    rows, bad = [], []
    for r in client.messages.batches.results(a.batch_id):
        s, d = r.custom_id.split("|")
        if r.result.type != "succeeded":
            bad.append((r.custom_id, r.result.type)); continue
        msg = r.result.message
        summ, err = parse_message(msg)
        if err:
            bad.append((r.custom_id, err)); continue
        rows.append(row(s, d, msg.model, summ, msg.usage))
    os.makedirs(f"{a.workdir}/summaries", exist_ok=True)
    with open(f"{a.workdir}/summaries/{a.batch_id}.jsonl", "w") as f:
        for x in rows:
            f.write(json.dumps(x) + "\n")
    with db.change_note(f"Earnings-call key points, prompt {PROMPT_VERSION}, batch {a.batch_id}"):
        db.upsert("transcript_summaries", rows, on_conflict="symbol,call_date,prompt_version,model")
    print(f"stored {len(rows)}, failed {len(bad)}: {bad[:10]}")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd", required=True)
    x = sub.add_parser("pilot"); x.add_argument("workdir"); x.add_argument("--n", type=int, default=30)
    x.add_argument("--models", default="claude-opus-5-5,claude-haiku-5-5")
    x = sub.add_parser("submit"); x.add_argument("workdir"); x.add_argument("--model", default="claude-opus-5-5")
    x.add_argument("--years"); x.add_argument("--limit", type=int)
    x = sub.add_parser("collect"); x.add_argument("workdir"); x.add_argument("batch_id")
    a = p.parse_args()
    {"pilot": cmd_pilot, "submit": cmd_submit, "collect": cmd_collect}[a.cmd](a)
