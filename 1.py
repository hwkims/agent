import requests
import pyautogui
from PIL import ImageGrab
import io
import json
import time
from pynput.keyboard import Controller
import base64
import re  # 정규 표현식 모듈 추가


# Ollama API 엔드포인트
OLLAMA_API_URL = "http://192.168.0.119:11434/api/chat"

# 사용할 모델
MODEL_NAME = "llama3.2-vision"

# PyAutoGUI fail-safe 비활성화
pyautogui.FAILSAFE = False

# 액션 간 딜레이
ACTION_DELAY = 0.5

# 최대 재시도 횟수
MAX_RETRIES = 3

# pynput 키보드 컨트롤러
keyboard = Controller()

# 명령어와 함수 매핑
ACTION_MAPPING = {
    "click": lambda x, y: pyautogui.click(x=int(x), y=int(y)),
    "doubleclick": lambda x, y: pyautogui.doubleClick(x=int(x), y=int(y)),
    "rightclick": lambda x, y: pyautogui.rightClick(x=int(x), y=int(y)),
    "type": lambda text: keyboard.type(str(text)),
    "keydown": lambda key: pyautogui.keyDown(str(key)),
    "keyup": lambda key: pyautogui.keyUp(str(key)),
    "press": lambda key: pyautogui.press(str(key)),
    "moveto": lambda x, y, duration=0.2: pyautogui.moveTo(x=int(x), y=int(y), duration=float(duration)),
    "scroll": lambda clicks: pyautogui.scroll(int(clicks)),
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
    """Ollama 응답 파싱 (정규 표현식으로 JSON 추출)"""
    try:
        if "message" in response_json and "content" in response_json["message"]:
            response_content = response_json["message"]["content"]

            # 정규 표현식을 사용하여 JSON 객체 추출 (더 유연하게)
            match = re.search(r"\{.*\}", response_content, re.DOTALL)
            if match:
                json_str = match.group(0)
                try:
                    response_data = json.loads(json_str)
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
    """액션 수행 (성공/실패 여부 반환)"""
    if action in ACTION_MAPPING:
        try:
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

def generate_refined_prompt(user_prompt, last_action=None, last_params=None, last_success=None):
    """향상된 프롬프트 생성"""
    prompt = f"""
You are a helpful assistant that controls the computer based on the user's request, the current screen image, and the history of previous actions.
Your response MUST be in JSON format, and include an 'action' key and a 'params' key. The 'params' value MUST be a dictionary.

Available actions are: {list(ACTION_MAPPING.keys())}

Here's how to format your JSON response:

{{
  "action": "click",
  "params": {{"x": 100, "y": 200}}
}}

{{
  "action": "type",
  "params": {{"text": "hello world"}}
}}

User's request: {user_prompt}
"""
    if last_action:
        prompt += f"\nLast action: {last_action}"
    if last_params:
        prompt += f"\nLast action parameters: {last_params}"
    if last_success is not None:
        prompt += f"\nLast action success: {last_success}"

    return prompt



if __name__ == "__main__":
    print("실시간 화면 기반 컴퓨터 자동화 (Ollama API) 시작. '종료'라고 입력하면 끝납니다.")
    user_prompt = input("무엇을 해드릴까요? > ")

    last_action = None
    last_params = None
    last_success = None


    while user_prompt.lower() != "종료":
        screen_base64 = capture_screen_and_encode()
        if not screen_base64:
            print("화면 캡처 실패. 다시 시도해주세요.")
            user_prompt = input("무엇을 해드릴까요? > ")
            continue

        prompt = generate_refined_prompt(user_prompt, last_action, last_params, last_success)
        response = call_ollama_api(prompt, screen_base64)

        if response:
            action, params, error_msg = parse_ollama_response(response)
            if action and params:
                success = perform_action(action, params)
                last_action = action  # 이전 액션 정보 업데이트
                last_params = params
                last_success = success
                if success:
                    user_prompt = input("다음 명령을 입력하세요 ('종료'로 종료): ") #성공시 다음 행동
                else:

                    retry_prompt = input("액션 수행 실패.  다시 시도하시겠습니까? (y/n): ") # 실패시 재시도
                    if retry_prompt.lower() != 'y':
                        user_prompt = "종료" #재시도를 안할경우 종료

            elif error_msg:
                print(f"모델 응답 오류: {error_msg}")
                user_prompt = input("다른 명령을 입력해주세요 ('종료'로 종료): ")

            else:  # 파싱은 성공했지만, 유효한 action/params가 없을 때
                print("유효한 액션을 받지 못했습니다.")
                user_prompt = input("다른 명령을 입력해주세요 ('종료'로 종료): ")
        else:
            print("API 응답을 받지 못했습니다.")
            user_prompt = input("다른 명령을 입력해주세요 ('종료'로 종료): ")

    print("프로그램을 종료합니다.")
    pyautogui.FAILSAFE = True
