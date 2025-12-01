# musinsa_snap

무신사 스냅 사진과 태그를 수집하기 위한 간단한 스크립트입니다. 페이지를 순회하며 스냅 상세 페이지를 조회하고, 사진 URL·작성자·태그 등의 메타데이터를 JSON Lines 파일로 저장합니다.

## 실행 방법

1. 의존성 설치
   ```bash
   pip install -r requirements.txt
   ```

2. 스크래핑 실행
   ```bash
   python -m musinsa_snap.cli --start-page 1 --end-page 2 --limit 20 --output snaps.jsonl --delay 0.5
   ```

   주요 옵션
   - `--start-page` / `--end-page`: 수집할 리스트 페이지 범위
   - `--limit`: 최대 수집 스냅 수 (선택)
   - `--delay`: 요청 간 대기 시간(초)
   - `--output`: 저장할 JSON Lines 파일 경로
   - `--verbose`: 상세 로그 출력

## 수집 결과 예시

`snaps.jsonl` 파일에는 한 줄당 하나의 스냅 정보가 JSON으로 기록됩니다.

```json
{"id": "123456", "url": "https://www.musinsa.com/mz/snap/123456", "title": "겨울 아우터", "author": "musinsa", "image_url": "https://image.msscdn.net/123456.jpg", "tags": ["패딩", "무지"], "taken_at": "2024.12.01", "description": "따뜻한 겨울 코디"}
```

## 참고

- 스냅 상세 페이지의 마크업이 변경될 수 있으므로, 필요한 경우 `musinsa_snap/parser.py`의 CSS 선택자를 조정해 주세요.
- 사이트에 부하를 주지 않도록 `--delay` 옵션으로 요청 간격을 두고, 필요한 범위만 수집하시길 권장합니다.
