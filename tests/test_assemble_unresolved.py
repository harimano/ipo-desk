from collector.assemble import merge_unresolved
from collector.result import Result


def _res(module, ok, notes=()):
    r = Result(module=module)
    r.ok = ok
    r.unresolved = list(notes)
    return r


def test_unresolved_is_current_state_not_a_log():
    prev = ["db-era note nobody can resolve", "[gmp] old gmp note", "[listings] no symbol on X", "[flows] kept"]
    out = merge_unresolved(prev, [_res("gmp", True, ["new gmp note"]), _res("listings", False), _res("news", True)])
    assert out == ["[listings] no symbol on X", "[flows] kept", "[gmp] new gmp note"]
    assert merge_unresolved(out, [_res("gmp", True, ["new gmp note"])]).count("[gmp] new gmp note") == 1
