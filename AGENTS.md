# AGENTS.md

## Version Control

- `code-update-by-agent` 브랜치가 없으면 생성한다.
- 하나의 요청에 해당하는 작업이 완료되면 `code-update-by-agent` 브랜치에 즉시 커밋한다.
- `code-update-by-agent` 브랜치가 current branch보다 뒤에 있는 경우 `code-update-by-agent` 브랜치를 재생성한다.
- 사용자가 rebase를 했을 수 있으므로 `code-update-by-agent`의 커밋이 사라지거나 히스토리가 바뀌어 있어도 정상적인 상황으로 간주한다.
- 커밋 메시지 첫 줄은 `<type>: <short summary>` 형태로 작성하고, `type`은 다음 중 하나를 선택한다: `build, chore, ci, docs, feat, fix, perf, refactor, revert, style, test`
- 나머지 메시지는 한국어로 작성한다.
- 작업 내용은 명사형으로 간결하게 작성한다.

## Response Style

- Respond concisely.
