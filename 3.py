import requests
import pyautogui
from PIL import ImageGrab, Image
import io
import json
import time
from pynput.keyboard import Controller, Key
import base64
import re

# Ollama API 엔드포인트
OLLAMA_API_URL = "http://192.168.0.119:11434/api/chat"  # 실제 주소로 변경

# 사용할 모델
MODEL_NAME = "llama3.2-vision"  # 적절한 모델 이름으로 변경

# PyAutoGUI fail-safe 비활성화
pyautogui.FAILSAFE = False

# 액션 간 딜레이
ACTION_DELAY = 0.5

# 최대 재시도 횟수
MAX_RETRIES = 3

# pynput 키보드 컨트롤러
keyboard = Controller()

# 명령어와 함수 매핑 (scroll 파라미터 수정)
ACTION_MAPPING = {
    "click": lambda x, y: pyautogui.click(x=int(x), y=int(y)),
    "doubleclick": lambda x, y: pyautogui.doubleClick(x=int(x), y=int(y)),
    "rightclick": lambda x, y: pyautogui.rightClick(x=int(x), y=int(y)),
    "type": lambda text: keyboard.type(str(text)),
    "keydown": lambda key: pyautogui.keyDown(str(key)),
    "keyup": lambda key: pyautogui.keyUp(str(key)),
    "press": lambda key: pyautogui.press(str(key)),
    "moveto": lambda x, y, duration=0.2: pyautogui.moveTo(x=int(x), y=int(y), duration=float(duration)),
    "scroll": lambda clicks, x=None, y=None: pyautogui.scroll(int(clicks), x=int(x) if x else None, y=int(y) if y else None),
    "pagedown": lambda: keyboard.press(Key.page_down), # Page Down 키 추가
    "wait": lambda seconds: time.sleep(float(seconds)),
}


def capture_screen_and_encode():
    """화면 캡처 후 base64 인코딩"""
    try:
        screenshot = ImageGrab.grab()
        buffered = io.BytesIO()
        screenshot.save(buffered, format="PNG")
        return base64.b64encode(buffered.getvalue()).decode()
    except Exception as e:
        print(f"화면 캡처 오류: {e}")
        return None


def call_ollama_api(prompt, image_base64=None):
    """Ollama API 호출 (재시도 로직 포함)"""
    headers = {"Content-Type": "application/json"}
    data = {
        "model": MODEL_NAME,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "format": "json",
    }
    if image_base64:
        data["messages"][0]["images"] = [image_base64]

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.post(OLLAMA_API_URL, headers=headers, data=json.dumps(data))
            response.raise_for_status()
            return response.json()
        except requests.exceptions.RequestException as e:
            print(f"API 호출 오류 (시도 {attempt + 1}/{MAX_RETRIES}): {e}")
            time.sleep(2 ** attempt)  # Exponential backoff
    print(f"API 호출 실패 (최대 재시도 횟수 초과)")
    return None



def parse_ollama_response(response_json):
    """Ollama 응답 파싱 (정규 표현식으로 JSON 추출) 및 reasoning 출력"""
    try:
        if "message" in response_json and "content" in response_json["message"]:
            response_content = response_json["message"]["content"]
            print(f"Ollama 원시 응답: {response_content}")  # 원시 응답 출력

            # 정규 표현식을 사용하여 JSON 객체 추출
            match = re.search(r"\{.*\}", response_content, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    response_data = json.loads(json_str)
                    print(f"파싱된 JSON 응답: {response_data}")  # 파싱된 응답 출력

                    # reasoning 출력
                    if "reasoning" in response_data:
                        print(f"Reasoning: {response_data['reasoning']}")

                    if "action" in response_data and "params" in response_data:
                         if isinstance(response_data["params"], dict):
                            return response_data["action"], response_data["params"], None
                         else:
                            return None, None, "params가 딕셔너리 형태가 아닙니다."

                    else:
                        return None, None, "응답에 'action' 또는 'params' 키가 없습니다."
                except json.JSONDecodeError:
                    return None, None, "응답 내용이 유효한 JSON 형식이 아닙니다."
            else:
                return None, None, "응답에서 JSON 객체를 찾을 수 없습니다."
        else:
            return None, None, "응답에 'message' 또는 'content' 키가 없습니다."
    except Exception as e:
        print(f"응답 파싱 오류: {e}")
        return None, None, str(e)



def perform_action(action, params):
    """액션 수행 (성공/실패 여부 반환, clarify 추가)"""
    if action == "clarify":
        print(params["message"])
        return True

    if action in ACTION_MAPPING:
        try:
            if action == "scroll":
                #scroll 동작에 clicks 가 정의되지 않아 생기는 문제 해결
                ACTION_MAPPING[action](clicks=params.get('y',0))
            else:
                ACTION_MAPPING[action](**params)
            print(f"'{action}' 동작 수행 완료: {params}")
            time.sleep(ACTION_DELAY)
            return True
        except (TypeError, ValueError, Exception) as e:
            print(f"'{action}' 동작 수행 중 오류: {e}")
            return False
    else:
        print(f"알 수 없는 동작: {action}")
        return False


def generate_initial_prompt(user_prompt):
    """초기 프롬프트 생성 (reasoning 추가)"""
    return f"""
You are a helpful assistant that controls the computer based on the user's request and the current screen image.  
Your response MUST be in JSON format, and include an 'action' key, a 'params' key, and a 'reasoning' key.  
The 'params' value MUST be a dictionary. The 'reasoning' should explain *why* you chose that action and params based on what you see on the screen.

Available actions are: {list(ACTION_MAPPING.keys())}

Here's how to format your JSON response:

{{
  "action": "click",
  "params": {{"x": 100, "y": 200}},
  "reasoning": "I see a button at coordinates (100, 200) that says 'Submit'.  Clicking it will likely proceed to the next step."
}}

{{
  "action": "type",
  "params": {{"text": "hello world"}},
  "reasoning": "There is a text input field near the top of the screen.  The user probably wants to enter 'hello world' into this field."
}}

{{
    "action": "pagedown",
    "params": {{}},
    "reasoning": "Scrolling down using the mouse wheel did not work. Pressing the Page Down key is the next best alternative to scroll down."
}}

If the user's request is too vague or cannot be directly executed, respond with JSON like this:

{{
    "action": "clarify",
    "params": {{"message": "Please provide more specific instructions.  For example, tell me which game you want to play."}},
    "reasoning": "The user's request is too general. I need more information to understand what they want to do."
}}

User's request: {user_prompt}
"""


def generate_feedback_prompt(last_action, last_params, last_success):
    """피드백 프롬프트 생성 (reasoning 추가)"""
    prompt = f"""
You are a helpful assistant that controls the computer. You are provided with the previous action, its parameters, and whether it was successful.
Based on this information and the current screen image, determine the next action to perform.
Your response MUST be in JSON format, and include an 'action' key, a 'params' key, and a 'reasoning' key.
The 'params' value MUST be a dictionary. The 'reasoning' should explain *why* you chose that action and its parameters.

Available actions are: {list(ACTION_MAPPING.keys())}

Here's how to format your JSON response:

{{
  "action": "click",
  "params": {{"x": 100, "y": 200}},
  "reasoning": "Based on the previous action, a new window has appeared. I see a button labeled 'OK' at coordinates (100,200), and clicking it seems like the next logical step."
}}

{{
  "action": "type",
  "params": {{"text": "hello world"}},
   "reasoning": "The previous click opened a text field.  The next step is to type 'hello world' into that field."

}}

{{
    "action": "pagedown",
    "params": {{}},
    "reasoning": "Scrolling down using the mouse wheel did not work. Pressing the Page Down key is the next best alternative to scroll down."
}}

If the user's request is too vague or cannot be directly executed, respond with JSON like this:

{{
    "action": "clarify",
    "params": {{"message": "Please provide more specific instructions.  For example, tell me which specific file to open."}},
    "reasoning": "I see many files on the screen, but I don't know which one the user is referring to."
}}

Last action: {last_action}
Last action parameters: {last_params}
Last action success: {last_success}
"""
    return prompt



if __name__ == "__main__":
    print("실시간 화면 기반 컴퓨터 자동화 (Ollama API, 무한 루프) 시작. Ctrl+C로 종료.")

    # 초기 사용자 입력 받기
    user_prompt = input("무엇을 해드릴까요? > ")
    initial_prompt = generate_initial_prompt(user_prompt)

    # 초기 상태 설정
    last_action = None
    last_params = None
    last_success = None
    current_prompt = initial_prompt

    try:
        while True:  # 무한 루프
            screen_base64 = capture_screen_and_encode()
            if not screen_base64:
                print("화면 캡처 실패. 잠시 후 다시 시도합니다.")
                time.sleep(2)  # 잠시 대기 후 재시도
                continue

            # API 호출
            response = call_ollama_api(current_prompt, screen_base64)

            if response:
                action, params, error_msg = parse_ollama_response(response)

                if action and params:
                    # 액션 수행
                    success = perform_action(action, params)
                    last_action = action
                    last_params = params
                    last_success = success

                    # 다음 프롬프트는 피드백 프롬프트
                    current_prompt = generate_feedback_prompt(last_action, last_params, last_success)

                elif error_msg:
                    print(f"모델 응답 오류: {error_msg}")
                    # 오류 발생 시, 초기 프롬프트로 복귀 (또는 다른 처리)
                    current_prompt = initial_prompt  # 이전 상태로 롤백
                else:
                    print("유효한 액션을 받지 못했습니다.")
                     # 유효한 액션이 없을 경우, 초기 프롬프트로 복귀
                    current_prompt = initial_prompt  # 이전 상태로 롤백
            else:
                print("API 응답을 받지 못했습니다. 잠시 후 다시 시도합니다.")
                time.sleep(2) # 잠시 대기
                current_prompt = initial_prompt  # api응답 없을 경우에도 초기 프롬프트로

    except KeyboardInterrupt:
        print("\nCtrl+C 입력 감지. 프로그램을 종료합니다.")
    finally:
        print("Fail-Safe 기능이 다시 활성화되었습니다.")
        pyautogui.FAILSAFE = True
