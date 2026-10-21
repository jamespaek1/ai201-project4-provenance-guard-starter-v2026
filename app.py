#!/usr/bin/env python3
"""
Provenance Guard — the web service.

    python app.py

Then, in another terminal:

    curl -X POST http://127.0.0.1:5000/ping \
      -H "Content-Type: application/json" \
      -d '{"message": "hello"}'

That's the example route. It works right now, before you've written anything.
**Leave it alone** — it's your control. When something breaks later, check that
`/ping` still answers: if it does, the problem is in your handler; if it
doesn't, it's the service itself.

Routes:

    POST /ping        the worked example. Already works. Don't edit it
    POST /submit      validate, score, label and record writing
    POST /appeal      record a challenge without rescoring
    GET  /content/id  original decision, current status and appeal history
    GET  /log         the audit log. Already works
    GET  /health      is the service up, and is the model loaded
"""

import uuid

from werkzeug.exceptions import BadRequest, RequestEntityTooLarge

from flask import Flask, jsonify, request

import audit
import config
import detector
import scoring
import stylometry

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = config.MAX_REQUEST_BYTES


def error_response(code, message, status):
    return jsonify({"error": code, "message": message}), status


@app.errorhandler(RequestEntityTooLarge)
def request_too_large(exc):
    return error_response("payload_too_large", "Request body must not exceed 64 KiB.", 413)


def json_object():
    if not request.is_json:
        return None, error_response("json_required", "Send application/json.", 415)
    try:
        payload = request.get_json()
    except BadRequest:
        return None, error_response("invalid_json", "The request body must be valid JSON.", 400)
    if not isinstance(payload, dict):
        return None, error_response("invalid_object", "The JSON body must be an object.", 400)
    return payload, None


def decision_for(content_id):
    events = audit.entries_for(content_id)
    decision = next((e for e in events if "guess" in e and e.get("status") == "decided"), None)
    return decision, events



# ── Rate limiting — UNIT 8 ────────────────────────────────────────────────────
# Off until you turn it on. In unit 8, Milestone 1:
#
#   1. Set RATE_LIMITING_ENABLED = True in config.py (or AI201_RATE_LIMITS=1)
#   2. Choose your numbers there
#   3. Uncomment the @limiter.limit(...) line on /submit below
#
# The order doesn't matter. While limiting is off, that decorator is a no-op
# that quietly does nothing, so uncommenting it early costs you nothing — but
# it also means no 429 until you've done step 1.
#
# The storage backend is preconfigured, which stops Flask-Limiter printing a
# warning on every start. In-memory is right for one laptop and wrong for
# anything real — a restart forgets every count.

class _LimiterOff:
    """
    Stands in for the real limiter while rate limiting is off.

    It makes @limiter.limit(...) a decorator that returns the route
    untouched, so uncommenting the line before you flip the setting is
    harmless instead of a crash on startup.
    """

    def limit(self, *args, **kwargs):
        return lambda view: view


limiter = _LimiterOff()
if config.RATE_LIMITING_ENABLED:
    from flask_limiter import Limiter
    from flask_limiter.util import get_remote_address

    def rate_limit_key():
        """
        Who a request counts against.

        Falling back to the caller's address is the easy version. Unit 8's
        stretch asks about per-creator limits instead — and the difference
        matters: one script can look like a thousand callers, and one household
        can look like one.
        """
        payload = request.get_json(silent=True)
        # A body that parses as JSON but isn't an object — a bare list or
        # string — has no .get. Without this guard the key function raises
        # BEFORE the route runs, and a malformed request becomes a 500 that
        # looks like your handler crashed when your handler never ran.
        if not isinstance(payload, dict):
            return get_remote_address()
        creator = payload.get("creator_id")
        return creator if isinstance(creator, str) and creator.strip() else get_remote_address()

    limiter = Limiter(
        key_func=rate_limit_key,
        app=app,
        storage_uri=config.RATE_LIMIT_STORAGE,
        default_limits=[],
    )

    @app.errorhandler(429)
    def rate_limited(exc):
        """
        A rejected request still leaves a trace.

        ⚠️ An attack that shows up only as an absence is one you'll never find.
        """
        payload = request.get_json(silent=True)
        if not isinstance(payload, dict):
            payload = {}
        audit.log_rejection(
            creator_id=payload.get("creator_id", "unknown"),
            reason="rate_limited",
            limit=str(exc.description),
        )
        return jsonify({
            "error": "rate_limited",
            "message": "Too many submissions. Try again shortly.",
            "limit": str(exc.description),
        }), 429


# ── The worked example. Already works. Don't edit. ────────────────────────────

@app.post("/ping")
def ping():
    """
    Everything a route needs, in six lines.

    JSON arrives as a dict. You pull things out of it. You return a dict and
    the framework turns it into a response. That's the whole idea.
    """
    payload = request.get_json(silent=True) or {}
    return jsonify({
        "ok": True,
        "you_sent": payload.get("message"),
        "service": "provenance-guard",
    })


@app.get("/health")
def health():
    """Is the service up, and has the model been downloaded yet?"""
    import detector

    loaded = detector._model is not None
    return jsonify({
        "ok": True,
        "detector_model": config.DETECTOR_MODEL,
        "detector_loaded": loaded,
        "rate_limiting": config.RATE_LIMITING_ENABLED,
        "log_entries": len(audit.read_entries()),
    })


# ── Unit 7 submission and appeal routes ───────────────────────────────────────

@app.post("/submit")
# @limiter.limit(f"{config.RATE_LIMIT_PER_MINUTE}/minute;{config.RATE_LIMIT_PER_DAY}/day")
def submit():
    """Validate input before inference; return and audit the two-signal decision."""
    payload, error = json_object()
    if error is not None:
        return error
    text, creator = payload.get("text"), payload.get("creator_id")
    if not isinstance(text, str) or not text.strip():
        return error_response("invalid_text", "text must be a nonempty string.", 400)
    if len(text) > config.MAX_TEXT_CHARACTERS:
        return error_response("text_too_large", "text must not exceed 10,000 characters.", 413)
    if len(stylometry.words(text)) < config.MIN_TEXT_WORDS:
        return error_response("text_too_short", "Provide at least 20 words for this estimate.", 400)
    if not isinstance(creator, str) or not creator.strip() or len(creator) > config.MAX_CREATOR_CHARACTERS:
        return error_response("invalid_creator", "creator_id must be a nonblank string of at most 100 characters.", 400)
    try:
        model_score = detector.model_signal(text)
        style_score = stylometry.style_signal(text)
        confidence = scoring.combine_signals(model_score, style_score)
        guess, label = scoring.score_to_label(confidence)
    except detector.DetectorUnavailable:
        return error_response("detector_unavailable", "The local model is unavailable. Try again after it is installed.", 503)
    except ValueError:
        return error_response("unscorable_text", "The model could not score this text. Try a longer passage.", 422)
    content_id = str(uuid.uuid4())
    entry = audit.log_decision(
        content_id=content_id, creator_id=creator, guess=guess,
        model_score=model_score, style_score=style_score, combined_score=confidence,
        label=label, status="decided", implementation_stage="two_signals",
    )
    return jsonify({**entry, "confidence": confidence,
        "appeal": {"endpoint": "/appeal", "method": "POST",
                   "required_fields": ["content_id", "reasoning"]},
        "score_meaning": "Higher scores indicate more AI-associated patterns; this is not an authorship probability.",
    })


@app.post("/appeal")
def appeal():
    """Append an appeal; the latest event supplies durable under-review status."""
    payload, error = json_object()
    if error is not None:
        return error
    content_id, reasoning = payload.get("content_id"), payload.get("reasoning")
    if not isinstance(content_id, str) or not content_id.strip():
        return error_response("invalid_content_id", "content_id must be a nonempty string.", 400)
    if not isinstance(reasoning, str) or not reasoning.strip() or len(reasoning) > config.MAX_REASONING_CHARACTERS:
        return error_response("invalid_reasoning", "reasoning must be a nonblank string of at most 2,000 characters.", 400)
    decision, events = decision_for(content_id)
    if decision is None:
        return error_response("content_not_found", "No submission has that content_id.", 404)
    entry = audit.log_appeal(content_id, decision["creator_id"], reasoning)
    return jsonify({"content_id": content_id, "status": entry["status"],
        "message": "Your explanation has been recorded and this item is under review. The original estimate remains in the history; no new assessment was made.",
        "reasoning": reasoning,
    })


@app.get("/content/<content_id>")
def get_content(content_id):
    """Declared stretch: reconstruct current status from persistent audit events."""
    decision, events = decision_for(content_id)
    if decision is None:
        return error_response("content_not_found", "No submission has that content_id.", 404)
    appeals = [e for e in events if e.get("event") == "appeal"]
    return jsonify({**decision, "confidence": decision.get("combined_score"),
        "status": "under_review" if appeals else decision["status"], "appeals": appeals,
    })


# ── Already works ─────────────────────────────────────────────────────────────

@app.get("/log")
def get_log():
    """
    The audit log, most recent last.

        curl "http://127.0.0.1:5000/log?limit=10"

    You need this in unit 8 to paste entries into your README, and you need it
    now to see whether your logging is actually working.
    """
    limit = request.args.get("limit", type=int)
    entries = audit.read_entries(limit=limit)
    return jsonify({"count": len(entries), "entries": entries})


def main():
    print(f"Provenance Guard on http://{config.HOST}:{config.PORT}")
    print(f"  detector model:  {config.DETECTOR_MODEL}")
    print(f"  rate limiting:   {'ON' if config.RATE_LIMITING_ENABLED else 'off (unit 8)'}")
    print(f"  audit log:       {config.AUDIT_LOG}")
    print()
    print("Check it's alive:")
    print(f'  curl -X POST http://{config.HOST}:{config.PORT}/ping \\')
    print('    -H "Content-Type: application/json" \\')
    print("    -d '{\"message\": \"hello\"}'")
    print()
    # debug=True hands out an interactive debugger, so it's local-only — see config.py
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)


if __name__ == "__main__":
    main()
