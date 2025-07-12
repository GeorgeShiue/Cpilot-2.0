import threading
from typing import List, Union

from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from tool import SearchExecutionTool, WebExecutionTool
from utils.factory import AgentFactory

class ExecutionAgent():
    # Response Class
    class Plan(BaseModel):
        """Plan to follow in future"""

        steps: List[str] = Field(
            description="different steps to follow, should be in sorted order"
        )

    class Response(BaseModel):
        """Response to user."""

        response: str

    class Act(BaseModel):
        """Action to perform."""

        action: Union['ExecutionAgent.Response', 'ExecutionAgent.Plan'] = Field(
            description="Action to perform. If you want to respond to user, use Response. "
            "If you need to further use tools to get the answer, use Plan."
        )

    def __init__(self, executor_name):
        self.executor_name = executor_name
        self.tool = self.init_execution_tool()
        self.planner, self.executor, self.replanner, self.solver = self.create_agents()

        

    def init_execution_tool(self):
        if self.executor_name == "Search Executor":
            execution_tool = SearchExecutionTool()
            return execution_tool
        elif self.executor_name == "Pipeline Executor":
            execution_tool = WebExecutionTool()

            # *啟動瀏覽器初始化執行緒
            self.create_browser_thread = threading.Thread(
                target=execution_tool.create_browser,
                daemon=True  # 確保主程式結束時，執行緒也會結束
            )
            self.create_browser_thread.start()

            return execution_tool
        else:
            raise ValueError("Invalid Executor name. Choose 'Search Executor' or 'Pipeline Executor'.")

    def create_planner_agent(self):
        # * Plannger Agent 使用 ChatPromptTemplate.from_messages() 搭配 with_structured_output(Plan) 實現
        llm_config, planner_system_prompt, tool_list = AgentFactory.extract_agent_parameter_yaml("Planner")

        planner_llm = ChatOpenAI(model=llm_config["model"], temperature=llm_config["temperature"])
        planner_prompt = ChatPromptTemplate.from_messages(
            [
                ("system", planner_system_prompt),
                ("placeholder", "{user_input}"), # placeholer 用來動態嵌入使用者輸入的訊息
            ]
        )

        AgentFactory.print_agent_parameter("Planner")

        planner = planner_prompt | planner_llm.with_structured_output(self.Plan) # 限制使用特定模板回答問題
        return planner

    def create_executor_agent(self):
        executor = AgentFactory.create_react_agent_with_yaml(self.executor_name, self.tool.tool_dict)
        return executor

    def create_replanner_agent(self):
        # * Replanner Agent 使用 ChatPromptTemplate.from_template() 搭配 with_structured_output(Act) 實現
        llm_config, replanner_system_prompt, tool_list = AgentFactory.extract_agent_parameter_yaml("Replanner")

        replanner_llm = ChatOpenAI(model=llm_config["model"], temperature=llm_config["temperature"]) # ! Replanner需要使用gpt-4o才不會一直call tools
        replanner_prompt = ChatPromptTemplate.from_template(replanner_system_prompt)
        
        AgentFactory.print_agent_parameter("Replanner")

        replanner = replanner_prompt | replanner_llm.with_structured_output(self.Act) # 限制使用特定模板回答問題
        return replanner

    def create_solver_agent(self):
        # * Solver Agent 使用 ChatPromptTemplate.from_template() 實現        
        llm_config, solver_system_prompt, tool_list = AgentFactory.extract_agent_parameter_yaml("Solver")

        solver_llm = ChatOpenAI(model=llm_config["model"])
        solver_prompt = ChatPromptTemplate.from_template(solver_system_prompt)

        AgentFactory.print_agent_parameter("Solver")

        solver = solver_prompt | solver_llm
        return solver
    
    def create_agents(self):
        planner = self.create_planner_agent()
        print("=" * 20)
        executor = self.create_executor_agent()
        print("=" * 20)
        replanner = self.create_replanner_agent()
        print("=" * 20)
        solver = self.create_solver_agent()

        return planner, executor, replanner, solver

    # def wait_browser_init(self):
    #     if self.create_browser_thread.is_alive():
    #         print("browser is starting...")
    #         self.create_browser_thread.join()
    #     print("browser is ready")  