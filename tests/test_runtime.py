import unittest

from personal_ai_agent.models import AgentTaskState, Artifact, PlanStep, StepResult, TaskBudget, TaskStatus
from personal_ai_agent.orchestrator import Orchestrator, WorkflowRegistry
from personal_ai_agent.state_machine import InvalidStateTransition, transition


class StateMachineTests(unittest.TestCase):
    def test_rejects_invalid_transition(self):
        state = AgentTaskState.create("thread-1", "test goal")
        with self.assertRaises(InvalidStateTransition):
            transition(state, TaskStatus.COMPLETED, "skip execution")


class OrchestratorTests(unittest.TestCase):
    def test_executes_dependencies_and_completes(self):
        order = []
        registry = WorkflowRegistry()

        def retrieve(state, step):
            order.append(step.step_id)
            return StepResult(artifacts=[Artifact("documents", ["doc-1"])], token_usage=10)

        def summarize(state, step):
            order.append(step.step_id)
            return StepResult(artifacts=[Artifact("summary", "result")], token_usage=20)

        registry.register("retrieve", retrieve)
        registry.register("summarize", summarize)
        state = AgentTaskState.create("thread-1", "summarize notes")
        steps = [
            PlanStep("s2", "analyze", "summarize", depends_on=("s1",)),
            PlanStep("s1", "retrieve", "retrieve"),
        ]

        result = Orchestrator(registry).run(state, steps)

        self.assertEqual(TaskStatus.COMPLETED, result.status)
        self.assertEqual(["s1", "s2"], order)
        self.assertEqual(30, result.token_usage)
        self.assertEqual(2, result.tool_calls)

    def test_bounds_step_retries(self):
        registry = WorkflowRegistry()

        def failing(state, step):
            raise RuntimeError("temporary failure")

        registry.register("failing", failing)
        state = AgentTaskState.create(
            "thread-1",
            "fail safely",
            budget=TaskBudget(max_tool_calls=10, max_step_retries=2),
        )

        result = Orchestrator(registry).run(
            state, [PlanStep("s1", "test", "failing")]
        )

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual(3, result.tool_calls)
        self.assertEqual(2, result.retry_count)
        self.assertEqual(3, len(result.errors))

    def test_rejects_cyclic_plan(self):
        state = AgentTaskState.create("thread-1", "cyclic plan")
        result = Orchestrator(WorkflowRegistry()).run(
            state,
            [
                PlanStep("s1", "test", "noop", depends_on=("s2",)),
                PlanStep("s2", "test", "noop", depends_on=("s1",)),
            ],
        )
        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual("InvalidPlan", result.errors[0].error_type)

    def test_plan_template_is_not_mutated_and_can_be_reused(self):
        registry = WorkflowRegistry()
        registry.register("work", lambda state, step: StepResult())
        template = [PlanStep("s1", "work", "work")]

        first = Orchestrator(registry).run(
            AgentTaskState.create("thread-1", "first"), template
        )
        second = Orchestrator(registry).run(
            AgentTaskState.create("thread-2", "second"), template
        )

        self.assertEqual(TaskStatus.COMPLETED, first.status)
        self.assertEqual(TaskStatus.COMPLETED, second.status)
        self.assertEqual("PENDING", template[0].status.value)
        self.assertEqual(0, template[0].attempt_count)

    def test_does_not_retry_deterministic_budget_failure(self):
        registry = WorkflowRegistry()

        def expensive(state, step):
            return StepResult(token_usage=101)

        registry.register("expensive", expensive)
        state = AgentTaskState.create(
            "thread-1", "respect budget", budget=TaskBudget(max_tokens=100)
        )

        result = Orchestrator(registry).run(
            state, [PlanStep("s1", "generate", "expensive")]
        )

        self.assertEqual(TaskStatus.FAILED, result.status)
        self.assertEqual(1, result.tool_calls)
        self.assertEqual(0, result.retry_count)
        self.assertEqual("BudgetExceeded", result.errors[0].error_type)


if __name__ == "__main__":
    unittest.main()
