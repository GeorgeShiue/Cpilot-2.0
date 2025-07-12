import operator
from typing import Annotated, Any, List, Tuple

from typing_extensions import TypedDict
from langgraph.graph import END, START, StateGraph

from agent import ExecutionAgent

class ExecutionGraph():
    class PlanExecute(TypedDict):
        input: str
        plan: List[str]
        past_steps: Annotated[List[Tuple], operator.add]
        response: str
        history: List[Tuple[str, Any]]

    def __init__(self, executor_name):
        self.executor_name = executor_name
        self.agent = ExecutionAgent(self.executor_name)
        self.graph = self.create_execution_graph()

    # * Define Agent Node Function, 不同 Agent Node Function 各自定義以實現訊息流區隔
    async def plan_step(self, state: PlanExecute):
        plan = await self.agent.planner.ainvoke({"user_input": [("user", state["input"])]}) # 對應到planner system prompt中的{user_input}
        state["history"].append(("Planner", plan.steps)) # 將plan的步驟加入history中

        return {
            "plan": plan.steps,
            "history": state["history"],
        }

    async def execute_step(self, state: PlanExecute):
        plan = state["plan"]
        plan_str = "\n".join(f"{i+1}. {step}" for i, step in enumerate(plan))
        task = plan[0]
        task_formatted = f"""For the following plan:
    {plan_str}\n\nYou are tasked with executing step {1}, {task}."""
        agent_response = await self.agent.executor.ainvoke({"messages": [("user", task_formatted)]}) # react agent 用 messages 方式接收訊息
        state["history"].append((self.executor_name, (task, agent_response["messages"][-1].content)))

        return {
            "past_steps": [(task, agent_response["messages"][-1].content)], # react agent 接收訊息方式
            "history": state["history"],
        }

    async def replan_step(self, state: PlanExecute):
        # 過濾掉state中不需要的欄位
        temp_state = state.copy()
        temp_state.pop("history")

        output = await self.agent.replanner.ainvoke(temp_state)
        if isinstance(output.action, ExecutionAgent.Response):
            state["history"].append(("Replanner", output.action.response))
            return {
                "response": output.action.response,
                "history": state["history"],
            }
        else:
            state["history"].append(("Replanner", output.action.steps))
            return {
                "plan": output.action.steps,
                "history": state["history"],
            }

    async def solve_step(self, state: PlanExecute):
        response = await self.agent.solver.ainvoke({"user_input": state["input"], "planning_history": state["history"]})
        return {"response": response.content, "history": state["history"]}

    # Define Conditional Edge Function
    def should_end(self, state: PlanExecute):
        if "response" in state and state["response"]:
            return "Solver"
        else:
            return self.executor_name
        
    def create_execution_graph(self):
        clean_graph = StateGraph(self.PlanExecute)

        # TODO node定義可以再更抽象化
        clean_graph.add_node("Planner", self.plan_step)
        clean_graph.add_node(self.executor_name, self.execute_step)
        clean_graph.add_node("Replanner", self.replan_step)
        clean_graph.add_node("Solver", self.solve_step)

        clean_graph.add_edge(START, "Planner")
        clean_graph.add_edge("Planner", self.executor_name)
        clean_graph.add_edge(self.executor_name, "Replanner")
        clean_graph.add_conditional_edges(
            "Replanner",
            # Next, we pass in the function that will determine which node is called next.
            self.should_end,
            [self.executor_name, "Solver"],
        )
        clean_graph.add_edge("Solver", END)

        graph = clean_graph.compile() # This compiles it into a LangChain Runnable, meaning you can use it as you would any other runnable
        # GraphFactory.save_graph_mermaid(graph, "Execution Graph") # 測試GraphFactory的save_graph_mermaid功能
        # print("Execution Graph is created.")

        return graph
    
    def set_screenshot_folder_path(self, screenshot_folder_path):
        self.agent.tool.selenium_controller.screenshot_folder_path = screenshot_folder_path
        print(f"Set screenshot folder path to: {screenshot_folder_path}")

    def wait_browser_init(self):
        if self.agent.create_browser_thread.is_alive():
            print("browser is starting...")
            self.agent.create_browser_thread.join()
        print("browser is ready")

    def get_current_screenshot_name(self):
        return self.agent.tool.current_screenshot_name



if __name__ == "__main__":
    import asyncio
    import os
    import shutil
    import time
    from dotenv import load_dotenv
    
    load_dotenv()
    api_key = os.getenv("API_KEY")
    os.environ["OPENAI_API_KEY"] = api_key

    execution_graph = ExecutionGraph("Search Executor")
    # evolution_graph = EvolutionGraph()