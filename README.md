# musinsa_snap

무신사 스냅 사진과 태그를 수집하기 위한 간단한 스크립트입니다. 실제 스냅 검색 URL(`https://www.musinsa.com/search/snap?keyword=...`)을 사용해 페이지를 순회하고, 스냅 상세 페이지를 조회하여 사진 URL·작성자·태그 등의 메타데이터를 JSON/CSV로 저장합니다. 추가로, 검색 키워드를 자동으로 입력하고 SNAP 탭을 클릭한 뒤 스크롤하며 이미지를 다운로드하는 Playwright 기반 자동화 도구를 제공합니다.

## 실행 방법

1. 의존성 설치
   ```bash
   pip install -r requirements.txt
   ```

2. 스크래핑 실행 (실제 스냅 검색 URL 기준)
```bash
 python -m musinsa_snap.cli "나이키" --gender M --start-page 1 --end-page 2 --limit 20 --delay 0.5 --json-out snaps.json --csv-out snaps.csv
```

   주요 옵션
   - `keyword`: 필수 검색어 (예: 나이키)
   - `--gender`: 성별 필터(`M` 또는 `F`, 미지정 시 전체)
   - `--start-page` / `--end-page`: 수집할 리스트 페이지 범위 (`https://www.musinsa.com/search/snap` 기준)
   - `--limit`: 최대 수집 스냅 수 (선택)
   - `--delay`: 요청 간 대기 시간(초)
   - `--retries`: HTTP 재시도 횟수
   - `--json-out`: JSON 배열 파일 경로
   - `--csv-out`: CSV 저장 경로 (선택)
   - `--verbose`: 상세 로그 출력
   - 기본 도메인은 `https://www.musinsa.com/`입니다. 필요 시 `--base-url` 혹은 `MusinsaClient(base_url=...)`로 교체할 수 있습니다.

### 검색 자동화 + 이미지/CSV/JSON 저장

1. Playwright 드라이버 설치(최초 1회)
   ```bash
   pip install -r requirements.txt
   playwright install chromium
   ```

2. 검색 태그 준비 (`musinsa_TAG.json`)

   기본 제공되는 `musinsa_TAG.json`에는 남녀 14개 카테고리(아우터/상의/셔츠/니트/팬츠/데님/신발)가 포함되어 있습니다. 원하는 검색어를 추가하거나 교체할 수 있습니다.

   ```json
   [
     {"label": "남성-아우터", "query": "남성 아우터 스냅"},
     {"label": "여성-니트", "query": "여성 니트 스냅"}
   ]
   ```

3. 자동화 실행 예시 (남/여 필터 포함)

   ```bash
   python -m musinsa_snap.automation \
     --tags-file musinsa_TAG.json \
     --gender M \
     --limit 10 \
     --output-dir downloads \
     --csv snaps.csv \
     --json snaps.json
   ```

   동작 요약 (요청하신 플로우)
   - 랜딩: `https://www.musinsa.com/main/musinsa/recommend?gf=M` (또는 `--gender F` 시 여성)
   - 메인 검색창에 `musinsa_TAG.json`의 검색어를 순차로 입력 후 SNAP/코디 탭 선택
   - 필터에서 남/여 버튼을 클릭해 성별을 고정
   - 최좌상단 SNAP 이미지를 한 번 열어 정상 연결을 확인한 뒤 닫고, 스크롤하며 상위 10개 스냅 링크를 수집
   - 각 스냅 상세에서 파란색 해시태그까지 모아 이미지 다운로드, CSV(`query,id,url,title,author,taken_at,tags,image_path`) 및 JSON(`snaps.json`) 저장

## 수집 결과 예시

`snaps.json` 파일은 스냅 정보를 JSON 배열로 저장합니다.

```json
[
  {"id": "123456", "url": "https://www.musinsa.com/snap/123456", "title": "겨울 아우터", "author": "musinsa", "image_url": "https://image.msscdn.net/123456.jpg", "tags": ["패딩", "무지"], "taken_at": "2024.12.01", "description": "따뜻한 겨울 코디"}
]
```

## 참고

- 스냅 상세 페이지의 마크업이 변경될 수 있으므로, 필요한 경우 `musinsa_snap/parser.py`의 CSS 선택자를 조정해 주세요.
- 사이트에 부하를 주지 않도록 `--delay` 옵션으로 요청 간격을 두고, 필요한 범위만 수집하시길 권장합니다.
