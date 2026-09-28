from flask import Flask, render_template, request, jsonify
import os
import base64
import json

from dotenv import load_dotenv
from openai import OpenAI


# ==================================================
# 1. 加载环境变量
# ==================================================

load_dotenv()

api_key = os.getenv("DEEPSEEK_API_KEY")

if not api_key:
    raise ValueError(
        "没有读取到 DEEPSEEK_API_KEY，请检查项目根目录下的 .env 文件"
    )


# ==================================================
# 2. 初始化 DeepSeek Client
# ==================================================

client = OpenAI(
    api_key=api_key,
    base_url="https://api.deepseek.com"
)


# ==================================================
# 3. 初始化 Flask
# ==================================================

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

app = Flask(
    __name__,
    template_folder=os.path.join(BASE_DIR, "templates")
)

UPLOAD_FOLDER = os.path.join(
    BASE_DIR,
    "uploads"
)

os.makedirs(
    UPLOAD_FOLDER,
    exist_ok=True
)

app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER


# ==================================================
# 3.1 Guided Mode API（S1 → S4 状态机，见 guided_routes.py）
# ==================================================

from guided_routes import guided_bp

app.register_blueprint(guided_bp)


# ==================================================
# 4. 首页
# ==================================================

@app.route("/")
def home():

    return render_template(
        "index.html"
    )


# ==================================================
# 5. 图片识别 API
# ==================================================

@app.route(
    "/api/recognize",
    methods=["POST"]
)
def recognize():

    # ----------------------------------------------
    # 检查图片
    # ----------------------------------------------

    if "image" not in request.files:

        return jsonify({
            "success": False,
            "message": "没有收到图片"
        }), 400


    image = request.files["image"]


    if image.filename == "":

        return jsonify({
            "success": False,
            "message": "没有选择图片"
        }), 400


    # ----------------------------------------------
    # 保存图片
    # ----------------------------------------------

    file_path = os.path.join(
        app.config["UPLOAD_FOLDER"],
        image.filename
    )

    image.save(file_path)

    print(
        f"收到图片：{file_path}"
    )


    # ----------------------------------------------
    # 图片转 Base64
    # ----------------------------------------------

    with open(
        file_path,
        "rb"
    ) as f:

        image_base64 = base64.b64encode(
            f.read()
        ).decode("utf-8")


    # ==================================================
    # 6. Vision Prompt
    # ==================================================

    prompt = """
请识别这张图片中的所有数学题，并严格按照下面的 JSON 格式返回。

要求：

1. 如果图片中有多道题，每一道大题作为一个独立的 question。
2. 保留题目的完整文字，包括小题编号、数字、单位和数学符号。
3. 不要解题。
4. subject 固定填写“数学”。
5. confidence 是你对该题文字识别结果的置信度，范围是 0 到 1。
6. 如果图片中存在无法确定的数学符号，请尽可能保留，并降低 confidence。
7. 只返回 JSON，不要添加解释。
8. 不要使用 Markdown 代码块。

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


    # ==================================================
    # 7. 调用 DeepSeek Vision
    # ==================================================

    try:

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

                                "url":
                                "data:image/jpeg;base64,"
                                + image_base64
                            }
                        }

                    ]
                }
            ]
        )


        result = (
            response
            .choices[0]
            .message
            .content
        )


        print(
            "\nDeepSeek 原始返回："
        )

        print(result)


    except Exception as e:

        print(
            "\nDeepSeek API 调用失败："
        )

        print(e)


        return jsonify({

            "success": False,

            "message":
            f"AI 识别失败：{str(e)}"

        }), 500


    # ==================================================
    # 8. 解析 JSON
    # ==================================================

    try:

        data = json.loads(
            result
        )


    except json.JSONDecodeError:

        print(
            "\nAI 返回的内容不是合法 JSON"
        )


        return jsonify({

            "success": False,

            "message":
            "AI 返回的数据格式不正确",

            "raw_result":
            result

        }), 500


    # ==================================================
    # 9. 检查 questions
    # ==================================================

    questions = data.get(
        "questions",
        []
    )


    if not isinstance(
        questions,
        list
    ):

        return jsonify({

            "success": False,

            "message":
            "AI 返回的 questions 不是列表"

        }), 500


    # ==================================================
    # 10. 返回前端
    # ==================================================

    return jsonify({

        "success": True,

        "message":
        "题目识别成功",

        "questions":
        questions

    })


# ==================================================
# 11. Quick Solve API
# ==================================================

@app.route(
    "/api/solve",
    methods=["POST"]
)
def solve():

    # ----------------------------------------------
    # 获取前端题目
    # ----------------------------------------------

    data = request.get_json(
        silent=True
    )


    if not data:

        return jsonify({

            "success": False,

            "message":
            "没有收到题目数据"

        }), 400


    question = (
        data
        .get("question", "")
        .strip()
    )


    if not question:

        return jsonify({

            "success": False,

            "message":
            "题目不能为空"

        }), 400


    print(
        "\n收到解题请求："
    )

    print(question)


    # ==================================================
    # 12. Quick Solve Prompt
    # ==================================================

    solve_prompt = f"""
你是一名严谨的数学老师。

请解决下面的数学题。

要求：

1. 给出正确答案。
2. 给出清晰、简洁的解题步骤。
3. 使用适合中小学生理解的语言。
4. 不要跳过关键计算。
5. 如果题目包含多个小题，请分别回答。
6. 不要编造题目中不存在的信息。
7. 最终答案必须明确。
8. 只返回 JSON。
9. 不要使用 Markdown 代码块。

请严格按照以下 JSON 格式返回：

{{
  "question": "{question}",
  "concept": "涉及的主要数学概念",
  "answer": "最终答案",
  "steps": [
    {{
      "step": 1,
      "explanation": "这一步做什么",
      "calculation": "具体计算"
    }}
  ],
  "final_answer": "最终答案"
}}

需要解决的题目：

{question}
"""


    # ==================================================
    # 13. 调用 DeepSeek
    # ==================================================

    try:

        response = client.chat.completions.create(

            model="deepseek-flash",

            messages=[

                {
                    "role": "user",

                    "content":
                    solve_prompt
                }

            ]
        )


        result = (
            response
            .choices[0]
            .message
            .content
        )


        print(
            "\nDeepSeek 解题原始返回："
        )

        print(result)


    except Exception as e:

        print(
            "\nDeepSeek 解题调用失败："
        )

        print(e)


        return jsonify({

            "success": False,

            "message":
            f"AI 解题失败：{str(e)}"

        }), 500


    # ==================================================
    # 14. 解析解题 JSON
    # ==================================================

    try:

        solution = json.loads(
            result
        )


    except json.JSONDecodeError:

        print(
            "\nAI 解题结果不是合法 JSON"
        )


        return jsonify({

            "success": False,

            "message":
            "AI 解题结果格式不正确",

            "raw_result":
            result

        }), 500


    # ==================================================
    # 15. 返回解题结果
    # ==================================================

    return jsonify({

        "success": True,

        "solution":
        solution

    })


# ==================================================
# 16. 健康检查 API
# ==================================================

@app.route(
    "/api/health",
    methods=["GET"]
)
def health():

    return jsonify({

        "success": True,

        "message":
        "AI 陪我学后端运行正常"

    })


# ==================================================
# 17. 启动 Flask
# ==================================================

if __name__ == "__main__":

    print(
        "\n========================================"
    )

    print(
        "AI 陪我学正在启动..."
    )

    print(
        f"项目目录：{BASE_DIR}"
    )

    print(
        f"模板目录：{app.template_folder}"
    )

    print(
        f"上传目录：{UPLOAD_FOLDER}"
    )

    print(
        "========================================\n"
    )


    app.run(

        host="0.0.0.0",

        port=5000,

        debug=True
    )