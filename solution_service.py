import os
import json

from dotenv import load_dotenv
from openai import OpenAI


# =========================
# 1. 加载环境变量
# =========================

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError(
        "没有读取到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件"
    )


# =========================
# 2. 初始化 DeepSeek Client
# =========================

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)


# =========================
# 3. 数学快速解题
# =========================

def solve_math_question(question_text):

    prompt = f"""
你是一名数学解题助手。

请解决下面这道数学题。

题目：
{question_text}

请严格按照下面的 JSON 格式返回：

{{
  "question": "题目原文",
  "concept": "这道题考查的主要数学知识点",
  "steps": [
    {{
      "step": 1,
      "explanation": "这一步在做什么",
      "calculation": "具体计算或推理"
    }}
  ],
  "final_answer": "最终答案"
}}

要求：

1. 必须认真完成数学计算。
2. 步骤按照实际解题顺序排列。
3. explanation 用简洁、适合学生理解的中文。
4. calculation 保留必要的数学表达式。
5. final_answer 必须明确。
6. 不要输出 Markdown。
7. 不要输出 JSON 以外的任何内容。
"""

    try:

        response = client.chat.completions.create(
            model="deepseek-flash",
            messages=[
                {
                    "role": "user",
                    "content": prompt
                }
            ]
        )

        result = response.choices[0].message.content

        print("\nDeepSeek 解题原始返回：")
        print(result)

    except Exception as e:

        print("\nDeepSeek 解题 API 调用失败：")
        print(e)

        return {
            "success": False,
            "message": f"AI 解题失败：{str(e)}"
        }


    # =========================
    # 4. 解析 JSON
    # =========================

    try:

        data = json.loads(result)

    except json.JSONDecodeError:

        print("\nAI 返回的内容不是合法 JSON")

        return {
            "success": False,
            "message": "AI 返回的数据格式不正确",
            "raw_result": result
        }


    # =========================
    # 5. 返回标准结果
    # =========================

    return {
        "success": True,
        "data": data
    }