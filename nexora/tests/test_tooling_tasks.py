"""The reference tasks of tooling_tasks.py, answered with the real tools."""

import json

import pytest

from nexora import api, tooling

from tooling_tasks import TASKS

TOOLS = {
    "check_source": tooling.check_source,
    "get_context": tooling.get_context,
    "get_symbols": tooling.get_symbols,
    "get_language_spec": tooling.get_language_spec,
    # The one task static analysis cannot answer uses the execution API, which is not an analysis tool.
    "run_source": api.run_source,
}


def answer(task: dict):
    tool = TOOLS[task["tool"]]
    arguments = task.get("arguments", {})
    if task["source"] is None:
        document = tool(**arguments)
    elif isinstance(task["source"], list):
        document = [tool(source, **arguments) for source in task["source"]]
    else:
        document = tool(task["source"], **arguments)
    return task["answer"](document)


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task["id"])
def test_task(task):
    assert answer(task) == task["expected"], task["question"]


@pytest.mark.parametrize("task", TASKS, ids=lambda task: task["id"])
def test_task_answers_are_reproducible(task):
    assert json.dumps(answer(task), default=str) == json.dumps(answer(task), default=str)


def test_the_set_of_tasks():
    assert len(TASKS) == 9
    assert len({task["id"] for task in TASKS}) == len(TASKS)
    assert all("?" in task["question"] for task in TASKS)
    # Only one task needs the program to run, and it says so by the tool it names.
    assert [task["id"] for task in TASKS if task["tool"] == "run_source"] == ["locate-a-broken-precondition"]
