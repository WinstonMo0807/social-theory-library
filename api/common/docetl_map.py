"""One bounded DocETL operator shared by local and remote computation workers."""
import io
from importlib.metadata import version
from types import SimpleNamespace


def run_map(model, prompt, data, schema, invoke):
    if version("docetl") != "0.3.0":
        raise ValueError("策展执行器需要已验证的DocETL 0.3.0。")
    from rich.console import Console
    from docetl.operations.map import MapOperation
    from docetl.operations.utils.llm import LLMResult
    results = []
    class API:
        def call_llm(self, selected_model, op_type, messages, output_schema, **kwargs):
            if selected_model != model or op_type != "map" or any(kwargs.get(k) for k in ("tools","gleaning_config","agent_config")):
                raise ValueError("DocETL试图使用未启用的模型、操作或工具。")
            text = "\n".join(m["content"] for m in messages)
            expected = prompt+"\n<source_data>"+data+"</source_data>"
            if text != expected:
                raise ValueError("DocETL改变了输入范围，停止执行。")
            result = invoke(text)
            results.append(result)
            return LLMResult(response=result.data,total_cost=0.0,validated=True)
    runner = SimpleNamespace(config={"bypass_cache":True},api=API(),is_cancelled=False)
    operation = MapOperation(runner,{"name":"stl_chapter","type":"map","model":model,
        "prompt":prompt+"\n<source_data>{{ input.source }}</source_data>",
        "output":{"schema":{key:"string" for key in schema.get("properties",{})}},
        "max_batch_size":1,"num_retries_on_validate_failure":0,"max_retries_per_timeout":0,
        "skip_on_error":False,"calibrate":False,"bypass_cache":True},
        default_model=model,max_threads=1,console=Console(file=io.StringIO()))
    rows,_ = operation.execute([{"source":data}])
    if len(rows) != 1 or len(results) != 1:
        raise ValueError("DocETL没有返回完整单窗口结果。")
    return results[0]
