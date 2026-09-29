# 루시안 딜량 계산기

리그 오브 레전드 챔피언 루시안의 스킬/평타 조합에 따른 데미지를 계산하는 웹 대시보드.

## 고려 요소
- 루시안 레벨별 기본 스탯 (공격력, 공속 등)
- 착용 아이템별 스탯 증가
- 착용 룬 효과
- 상대 챔피언의 레벨별 방어력/마법저항력

## 기술 스택
- Python (Streamlit)

## 구조
```
app/
  main.py            # Streamlit 앱 진입점
  models/            # 챔피언/아이템/룬 스탯 모델
  services/          # 데미지 계산 로직
data/                # 챔피언/아이템/룬 스탯 데이터
tests/               # 테스트
```

## 실행
```bash
pip install -r requirements.txt
streamlit run app/main.py
```
