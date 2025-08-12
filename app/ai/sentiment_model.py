# import os
# import time
# import torch
# from transformers import AutoTokenizer, AutoModelForCausalLM, BitsAndBytesConfig
# from transformers.utils import logging


# logging.set_verbosity_info()

# # 0. 환경 변수에서 HF 토큰 로드
# hf_token = os.getenv("HUGGINGFACE_HUB_TOKEN")
# if not hf_token:
#     raise ValueError("❌ HUGGINGFACE_HUB_TOKEN 환경변수가 없습니다.")

# # 1. 모델 로딩
# model_id = "google/gemma-2-2b-it"

# quant_config = BitsAndBytesConfig(
#     load_in_4bit=True,
#     bnb_4bit_quant_type="nf4",
#     bnb_4bit_compute_dtype=torch.bfloat16,
# )

# # 🔧 tokenizer 로드 (trust_remote_code 꼭 True)
# tokenizer = AutoTokenizer.from_pretrained(
#     model_id,
#     token=hf_token,
#     trust_remote_code=True
# )

# # 🔧 model 로드 (trust_remote_code 꼭 True)
# model = AutoModelForCausalLM.from_pretrained(
#     model_id,
#     token=hf_token,
#     device_map="auto",
#     trust_remote_code=True,
#     quantization_config=quant_config
# )

# # 🔍 모델 config 확인 로그 (선택 사항)
# print(f"✅ 모델 로드 완료: {model.config.model_type}")

# # 시스템 프롬프트 정의
# system_prompt = """너는 뉴스 기사 감정분석 전문가야.
# 주어진 기사를 읽고 다음 형식으로 분석해줘:

# **감정 분류**: 긍정적/부정적/중립적 중 하나  
# **신뢰도**: 0-100%  
# **주요 근거**: 판단 이유를 간단히 설명  
# **기사 의도**: 어떤 목적으로 작성되었는지 분석하고 전달하려는 메세지를 간결하게 정리해줘.
# **요약**: 기사의 핵심 내용을 2-3문장으로 요약해줘.

# 정확하고 객관적으로 분석해줘. 내가 지시하지 않은 내용은 포함하지 마.
# """

# # 2. 분석 함수
# def analyze_sentiment(content: str):
#     messages = [
#         {"role": "user", "content": f"{system_prompt}\n\n분석할 기사:\n{content}"}
#     ]
#     inputs = tokenizer.apply_chat_template(
#         messages,
#         tokenize=True,
#         add_generation_prompt=True,
#         return_tensors="pt"
#     ).to(model.device)

#     start_time = time.time()

#     with torch.no_grad():
#         outputs = model.generate(
#             inputs,
#             max_new_tokens=512,
#             temperature=0.7,
#             do_sample=True,
#             pad_token_id=tokenizer.eos_token_id
#         )

#     duration = round(time.time() - start_time, 2)

#     result = tokenizer.decode(outputs[0][inputs.shape[-1]:], skip_special_tokens=True)
#     return {
#         "analysis": result,
#         "inference_time_sec": duration
#     }
