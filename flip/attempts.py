"""Trying the models in turn, the same way for listings and messages.

In "auto" mode the local model goes first and an answer that fails the checks
gets one try on the paid model (a message gets one more free try on the local
model first, told what was wrong); "local" and "api" use one model only. A local
model that can't be reached (or isn't set up) stops there: nothing is sent to
the API in its place, so an item only leaves this Mac when a local answer has
failed the checks.
"""

from flip.costs import cost_pence

MODES = {"local": ["local"], "api": ["api"], "auto": ["local", "api"]}


def try_models(mode, models, ask, check, result, log=None, again=None, job="draft"):
    """Ask each model in turn until an answer passes check. ask(model) returns
    a Reply; check(answer) returns its problems. Every attempt is added to
    result["attempts"] (and the audit log); the passing answer is returned, or
    None with the reason added to result["reasons"]. again(model, answer,
    problems), if given: when the local model's answer fails the checks, one
    more try on this Mac, told what was turned down, before the paid model
    (free); it returns a Reply like ask."""
    def tried(reply):
        problems = [reply.error] if reply.answer is None else check(reply.answer)
        cost = cost_pence(reply.model, reply.tokens_in, reply.tokens_out)
        result["attempts"].append({"model": reply.model, "problems": problems, "seconds": reply.seconds,
                                   "tokens_in": reply.tokens_in, "tokens_out": reply.tokens_out, "cost_pence": cost})
        if log:
            log.attempt(result["item_id"], reply, problems, cost, job=job)  # "read" for reading the listing
        return problems

    for name in MODES[mode]:
        model = models.get(name)
        if model is None:
            result["reasons"].append(f"no {name} model is set up")
            if name == "local":
                return None  # never the API in place of a missing local model
            continue
        reply = ask(model)
        problems = tried(reply)
        if not problems:
            return reply.answer
        if name == "local" and not reply.reachable:
            result["reasons"].append(f"{reply.error}, and nothing was sent to the API instead")
            return None
        if name == "local" and again is not None and reply.answer is not None:
            reply = again(model, reply.answer, problems)
            if not tried(reply):
                return reply.answer
    result["reasons"].append("no answer passed the checks")
    return None
