from autogpt.core.configuration import SystemConfiguration, UserConfigurable
from autogpt.core.planning.base import PromptStrategy
from autogpt.core.planning.schema import (
    LanguageModelClassification,
    LanguageModelPrompt,
    TaskType,
    Task,
)
from autogpt.core.planning.strategies.utils import to_numbered_list, json_loads
from autogpt.core.resource.model_providers import LanguageModelMessage, LanguageModelFunction, MessageRole


class InitialPlanConfiguration(SystemConfiguration):
    model_classification: LanguageModelClassification = UserConfigurable()
    system_prompt_template: str = UserConfigurable()
    system_info: list[str] = UserConfigurable()
    user_prompt_template: str = UserConfigurable()
    create_plan_function: dict = UserConfigurable()


class InitialPlan(PromptStrategy):

    DEFAULT_SYSTEM_PROMPT_TEMPLATE = (
        "You are an augmented language model. This means that you are being used in a larger system "
        "to extend your functionality. This larger system provides you with a set of abilities you can use.\n\n"
        "Abilities:\n{abilities}\n\n"
        "The system will also manage your long term memory by storing information you collect and retrieving "
        "relevant information for the task you are working on. You should rely on the system for this "
        "and not attempt to manage your own memory.\n\n"
        "System Info:\n{system_info}"
    )

    DEFAULT_SYSTEM_INFO = [
        "The OS you are running on is: {os_info}",
        "It takes money to let you run. Your API budget is ${api_budget:.3f}",
        "The current time and date is {current_time}",
    ]

    DEFAULT_USER_PROMPT_TEMPLATE = (
        "You are {agent_name}, {agent_role}\n" "Your goals are:\n" "{agent_goals}"
        "You will accomplish your goals by breaking them down into "
        "a series of tasks and then executing those tasks one by one.\n"
        "Your first objective is to break down your goals into a series of small tasks by invoking the provided"
        "`create_initial_agent_plan` function.\n\n"
        "You should be able to accomplish each task with 1-3 uses of your abilities.\n"
        "You should make sure each task has clearly defined ready criteria so we can evaluate when the task can be started.\n"
        "You should also make sure each task has clearly defined acceptance criteria so we can evaluate when the task is complete.\n"
        "Smaller, well-defined tasks are highly preferable. Generate as many tasks as you think is necessary."
    )

    DEFAULT_CREATE_PLAN_FUNCTION = {
        "name": "create_initial_agent_plan",
        "description": "Creates a set of tasks that forms the initial plan for an autonomous agent.",
        "parameters": {
            "type": "object",
            "properties": {
                "task_list": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "objective": {
                                "type": "string",
                                "description": "An imperative verb phrase that succinctly describes the task.",
                            },
                            "type": {
                                "type": "string",
                                "description": "A categorization for the task. ",
                                "enum": [t.value for t in TaskType],
                            },
                            "acceptance_criteria": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "A list of measurable and testable criteria that must be met for the task to be considered complete.",
                                },
                            },
                            "priority": {
                                "type": "integer",
                                "description": "A number between 1 and 10 indicating the priority of the task relative to other generated tasks.",
                                "minimum": 1,
                                "maximum": 10,
                            },
                            "ready_criteria": {
                                "type": "array",
                                "items": {
                                    "type": "string",
                                    "description": "A list of measurable and testable criteria that must be met before the task can be started.",
                                },
                            },
                        },
                        "required": ["objective", "type", "acceptance_criteria", "priority", "ready_criteria"],
                    },
                },
            },
        }
    }

    default_configuration = InitialPlanConfiguration(
        model_classification=LanguageModelClassification.SMART_MODEL,
        system_prompt_template=DEFAULT_SYSTEM_PROMPT_TEMPLATE,
        system_info=DEFAULT_SYSTEM_INFO,
        user_prompt_template=DEFAULT_USER_PROMPT_TEMPLATE,
        create_plan_function=DEFAULT_CREATE_PLAN_FUNCTION,
    )

    def __init__(
        self,
        model_classification: LanguageModelClassification,
        system_prompt_template: str,
        system_info: list[str],
        user_prompt_template: str,
        create_plan_function: dict,
    ):
        self._model_classification = model_classification
        self._system_prompt_template = system_prompt_template
        self._system_info = system_info
        self._user_prompt_template = user_prompt_template
        self._create_plan_function = create_plan_function

    @property
    def model_classification(self) -> LanguageModelClassification:
        return self._model_classification

    def build_prompt(
        self,
        agent_name: str,
        agent_role: str,
        agent_goals: list[str],
        abilities: list[str],
        os_info: str,
        api_budget: float,
        current_time: str,
        **kwargs,
    ) -> LanguageModelPrompt:
        template_kwargs = {
            "agent_name": agent_name,
            "agent_role": agent_role,
            "os_info": os_info,
            "api_budget": api_budget,
            "current_time": current_time,
            **kwargs,
        }
        template_kwargs["agent_goals"] = to_numbered_list(agent_goals, **template_kwargs)
        template_kwargs["abilities"] = to_numbered_list(abilities, **template_kwargs)
        template_kwargs["system_info"] = to_numbered_list(self._system_info, **template_kwargs)

        system_prompt = LanguageModelMessage(
            role=MessageRole.SYSTEM,
            content=self._system_prompt_template.format(**template_kwargs),
        )
        user_prompt = LanguageModelMessage(
            role=MessageRole.USER,
            content=self._user_prompt_template.format(**template_kwargs),
        )
        create_plan_function = LanguageModelFunction(
            json_schema=self._create_plan_function,
        )

        return LanguageModelPrompt(
            messages=[system_prompt, user_prompt],
            functions=[create_plan_function],
            # TODO:
            tokens_used=0,
        )

    def parse_response_content(
        self,
        response_content: dict,
    ) -> dict:
        """Parse the actual text response from the objective model.

        Args:
            response_content: The raw response content from the objective model.

        Returns:
            The parsed response.

        """
        parsed_response = json_loads(response_content["function_call"]["arguments"])
        parsed_response["task_list"] = [
            Task.parse_obj(task) for task in parsed_response["task_list"]
        ]
        return parsed_response
