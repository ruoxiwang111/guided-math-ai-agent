import os
import base64
import json

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError("没有读取到 DEEPSEEK_API_KEY，请检查 .env 文件")

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)

# 测试图片
image_path = "test_math.jpg"

with open(image_path, "rb") as f:
    image_base64 = base64.b64encode(f.read()).decode("utf-8")

prompt = """
请识别这张图片中的所有数学题，并严格按照下面的 JSON 格式返回。

要求：
1. 如果图片中有多道题，每一道题都作为一个独立的 question。
2. 保留题目的完整文字，包括小题编号、数字、单位和数学符号。
3. 不要解题。
4. subject 固定填写“数学”。
5. confidence 是你对该题文字识别结果的置信度，范围是 0 到 1。
6. 只返回 JSON，不要添加任何解释、Markdown 或代码块。

JSON 格式：
{
  "questions": [
    {
      "id": 1,
      "text": "完整题目文字",
      "subject": "数学",
      "confidence": 0.98
    }
  ]
}
"""

response = client.chat.completions.create(
    model="deepseek-flash",
    messages=[
        {
            "role": "user",
            "content": [
                {
                    "type": "text",
                    "text": prompt
                },
                {
                    "type": "image_url",
                    "image_url": {
                        "url": f"data:image/jpeg;base64,{image_base64}"
                    }
                }
            ]
        }
    ]
)

result = response.choices[0].message.content

print("\nDeepSeek 原始返回：")
print(result)

print("\n解析后的 JSON：")

try:
    data = json.loads(result)
    print(json.dumps(data, ensure_ascii=False, indent=2))
except json.JSONDecodeError:
    print("⚠️ AI 返回的内容不是合法 JSON")