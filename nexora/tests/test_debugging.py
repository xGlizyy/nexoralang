from nexora.debugging import format_debug_value
from nexora.diagnostics import Source
from nexora.interpreter import run
from nexora.pipeline import analyze
from helpers import in_main


def test_statement_observer_stops_before_the_requested_statement():
    analysis = analyze(Source("debug.nex", in_main("let answer = 41\nprint(answer)\nprint(answer + 1)")))
    assert analysis.checked is not None
    output = []
    events = []

    def observe(event):
        events.append(event)
        return event.step == 3

    stopped = run(analysis.checked, output.append, debug_observer=observe)

    assert stopped is events[-1]
    assert stopped.step == 3
    assert stopped.span.line == 4
    assert stopped.function == "main"
    assert [frame.function for frame in stopped.call_stack] == ["main"]
    assert stopped.variables == (("answer", 41),)
    assert output == ["41\n"]


def test_debug_value_formatting_bounds_strings_and_nested_lists():
    rendered = format_debug_value("x" * 1000)
    assert len(rendered) <= 256
    assert rendered.endswith('…"')

    nested = tuple(tuple(tuple(range(100)) for _ in range(100)) for _ in range(100))
    assert len(format_debug_value(nested)) <= 256
