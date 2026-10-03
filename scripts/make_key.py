"""Run locally. Keep the generated key outside GitHub."""
from cryptography.fernet import Fernet
print('\n아래 값을 Streamlit Secrets의 ENCRYPTION_KEY에 붙여 넣으세요.\n')
print('ENCRYPTION_KEY = "' + Fernet.generate_key().decode() + '"')
print('\n기존 데이터가 있으면 새 키로 변경하지 마세요. 키를 잃으면 복구할 수 없습니다.\n')
