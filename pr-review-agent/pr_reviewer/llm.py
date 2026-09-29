from functools import lru_cache

from langchain_huggingface import HuggingFacePipeline
from langchain_core.prompts import PromptTemplate
from langchain_core.runnables import Runnable


@lru_cache(maxsize=2)
def build_summary_chain(model_id: str, task: str) -> Runnable:
    """Create the LangChain summarization chain (cached so the web service loads the model once)."""
    llm = HuggingFacePipeline.from_model_id(
        model_id=model_id,
        task=task,
        pipeline_kwargs={
            "max_new_tokens": 512,
            "return_full_text": False,
            "do_sample": False,
        },
    )
    prompt = PromptTemplate(
        input_variables=["context"],
        template="""You are an experienced code reviewer doing a pull request review. Read the PR metadata \
and code diffs below and write your review as plain text using EXACTLY this format (no JSON, no markdown fences):

Overview: <1-2 sentences on what this PR actually changes in the code and why>
Key Changes:
- <specific change, naming the file/function/config affected>
- <another specific change, add as many bullets as needed>
Suggestions:
- <a concrete bug, risk, missing test, or improvement you noticed in the diff>
- <write "No major concerns." if the diff looks fine>

Base every line on the diffs, not just the title. Be specific and skip generic filler.

PR Context:
{context}

Review:""",
    )
    return prompt | llm
