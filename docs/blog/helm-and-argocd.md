# Helm Chart & ArgoCD 제대로 이해하기 — 개념부터 Multi-source / Wrapper Chart까지

> Kubernetes에 애플리케이션을 배포하다 보면 결국 두 가지 도구를 만나게 된다. **Helm**(패키징·템플릿)과 **ArgoCD**(GitOps 배포). 이 글에서는 두 도구의 개념과 "왜 써야 하는가"에서 시작해, 실무에서 자주 헷갈리는 **single-source / multi-source**, **wrapper(umbrella) chart + vendored tgz**, **App-of-Apps**, **sync-wave** 같은 개념을 실제 설정 예시와 함께 정리한다.

---

## 1. 왜 이 두 도구가 필요한가

### 순수 `kubectl apply`의 한계

Kubernetes는 Deployment, Service, ConfigMap, Ingress 등 수많은 YAML 매니페스트로 구성된다. 작은 앱 하나도 매니페스트가 5~10개씩 나오고, Airflow 같은 스택은 수십 개에 달한다. 이걸 그냥 `kubectl apply -f`로 관리하면 다음 문제가 생긴다.

| 문제 | 설명 |
|------|------|
| **중복** | dev/staging/prod마다 거의 같은 YAML을 복사 → 값만 다른데 파일이 3벌 |
| **변수화 불가** | 이미지 태그, replica 수, 리소스 한도를 바꾸려면 YAML을 직접 수정 |
| **버전 관리/롤백 어려움** | "지금 클러스터에 뭐가 떠 있지?"를 추적하기 어려움 |
| **배포 드리프트(drift)** | 누군가 `kubectl edit`로 수동 변경 → Git과 클러스터 상태 불일치 |

→ **Helm**이 앞의 세 가지(중복·변수화·버전)를 해결하고, **ArgoCD**가 마지막(드리프트·GitOps)을 해결한다.

---

## 2. Helm — Kubernetes의 패키지 매니저

### 2.1 핵심 개념

Helm은 "apt/yum/npm 같은 패키지 매니저인데 대상이 Kubernetes 리소스"라고 생각하면 된다.

- **Chart**: 배포 단위 패키지. 템플릿 + 기본값 + 메타데이터의 묶음.
- **Values**: 차트에 주입하는 설정값. `values.yaml`이 기본값이고, `-f my-values.yaml`로 덮어쓴다.
- **Template**: `{{ .Values.image.tag }}` 같은 Go 템플릿 문법이 들어간 매니페스트. values를 주입해 최종 YAML로 렌더링된다.
- **Release**: 차트를 클러스터에 설치한 "인스턴스". 같은 차트를 이름만 다르게 여러 번 설치할 수 있다.

```
chart 디렉터리 구조
mychart/
├── Chart.yaml        # 차트 메타데이터 (이름, 버전, 의존성)
├── values.yaml       # 기본 설정값
├── charts/           # 의존 차트(서브차트)가 들어가는 곳
└── templates/        # 렌더링될 매니페스트 템플릿들
```

### 2.2 렌더링 흐름

```
values.yaml + (-f override.yaml)  ─┐
                                   ├──▶ helm template ──▶ 최종 K8s 매니페스트 ──▶ apply
templates/*.yaml ─────────────────┘
```

핵심은 **"템플릿 + 값 → 매니페스트"** 라는 단순한 함수다. 같은 차트에 값만 다르게 주면 dev/prod를 같은 코드로 찍어낼 수 있다.

### 2.3 Helm을 쓰면 좋은 점

1. **변수화**: 환경별 차이를 values 파일 하나로 분리.
2. **재사용**: 잘 만들어진 공식 차트(Airflow, Prometheus, VictoriaMetrics…)를 그대로 가져다 씀.
3. **버전·롤백**: 릴리스마다 리비전이 기록되어 `helm rollback` 가능.
4. **의존성 관리**: 한 차트가 다른 차트를 의존 관계로 끌어올 수 있음(서브차트).

---

## 3. Helm의 의존성 — Wrapper(Umbrella) Chart

여기서부터가 실무에서 자주 헷갈리는 부분이다. 공식 차트를 그대로 쓰되, **내 설정을 얹어서 관리하고 싶을 때** 쓰는 패턴이 wrapper chart다.

> **용어 메모.** Helm 공식 문서의 정식 명칭은 **umbrella chart**다. "wrapper chart"는 같은 개념을 가리키는 커뮤니티 통용어이니, 엄밀히 표기할 때는 *umbrella chart* 를 쓰는 게 좋다. ([Helm 공식 문서](https://helm.sh/docs/topics/charts/))

### 3.1 개념

내가 직접 만든 작은 차트가 **공식 차트를 의존성(dependency)으로 감싼다**. 내 차트에는 템플릿이 거의 없고, `Chart.yaml`에 "나는 apache의 airflow 차트 1.18.0에 의존한다"고 선언만 한다.

이 레포의 실제 예시(`helm_charts/airflow/Chart.yaml`):

```yaml
apiVersion: v2
name: airflow
type: application
version: 0.1.0

dependencies:
  - name: airflow
    repository: https://airflow.apache.org
    version: 1.18.0
```

→ "airflow라는 내 wrapper 차트는, apache 공식 airflow 차트 1.18.0을 서브차트로 끌어온다"는 뜻이다.

### 3.2 왜 wrapper로 감싸는가?

공식 차트를 ArgoCD에서 직접 가리켜도 되는데 왜 굳이 한 겹 더 씌울까?

- **버전을 Git에 고정**: 어떤 공식 차트 버전을 쓰는지 `Chart.yaml`/`Chart.lock`에 박혀서 코드 리뷰·이력 추적이 됨.
- **values를 한곳에 정리**: 내 환경 설정을 내 레포 안에서 관리.
- **여러 서브차트를 한 릴리스로 묶기**: 필요하면 의존성을 여러 개 추가해 한 번에 배포 가능.
- **약간의 커스터마이즈 추가 여지**: 공식 차트가 안 만들어주는 리소스(예: 추가 ConfigMap, Secret)를 내 `templates/`에 넣을 수 있음.

### 3.3 Chart.lock과 vendored tgz

의존성을 선언만 하면 끝이 아니다. 실제 서브차트 파일을 받아와야 한다.

```bash
# ① 의존성 해석 + 다운로드 + Chart.lock 생성/갱신 (버전 올릴 때)
helm dependency update helm_charts/airflow

# ② Chart.lock 기준으로 정확히 재현 다운로드 (CI/재현용, lock 안 바꿈)
helm dependency build helm_charts/airflow
```

`helm dependency update`를 돌리면:

1. `charts/` 디렉터리에 **`airflow-1.18.0.tgz`** 가 다운로드된다 → 이게 **vendored tgz**.
2. `Chart.lock`에 정확한 버전과 **digest(sha256)** 가 기록된다.

이 레포의 `Chart.lock`:

```yaml
dependencies:
- name: airflow
  repository: https://airflow.apache.org
  version: 1.18.0
digest: sha256:cacea8edf7be65efcd732ccb13f5f14b64faca1bc46d52879f5f4f7e27a3d075
generated: "2026-06-23T22:39:56.903123+09:00"
```

**Vendored tgz란?** 의존 차트를 외부 저장소에서 매번 받는 대신, `charts/` 안에 `.tgz`로 **함께 커밋(vendoring)** 해두는 방식이다.

> **용어 메모.** *vendoring* 은 Helm 공식 용어집에 정의된 단어는 아니지만(원래는 Go 등의 일반 소프트웨어 용어), Helm 공식 블로그·문서에서도 "vendored sub-charts", "vendor a chart" 형태로 통용된다. ([Helm 3 — Changes to Chart Dependencies](https://helm.sh/blog/helm-3-preview-pt5/))

| 항목 | tgz를 커밋(vendoring) | 매번 다운로드 |
|------|----------------------|---------------|
| **재현성** | 항상 동일 (digest 고정) | 원격 저장소 상태에 의존 |
| **외부 의존** | 없음 (오프라인/네트워크 장애에 강함) | 원격 repo가 죽으면 배포 실패 |
| **ArgoCD 호환** | ArgoCD가 별도 repo 접근 없이 렌더링 가능 | ArgoCD가 빌드 시 외부 접근 필요 |
| **레포 크기** | 커짐 | 작음 |

> ArgoCD는 기본적으로 매니페스트 생성 시 `helm dependency build`를 자동으로 돌려주지 않는 환경이 많아서, **서브차트 tgz를 미리 받아 커밋해 두는 vendoring**이 안전하다. 그래서 이 레포도 `charts/airflow-1.18.0.tgz`를 함께 둔다.

### 3.4 `update` vs `build` 차이 (꼭 기억)

- **`helm dependency update`**: `Chart.yaml`을 읽어 최신 상태로 받고 **`Chart.lock`을 새로 씀**. → 버전을 올릴 때.
- **`helm dependency build`**: **`Chart.lock`을 기준**으로 정확히 그 버전만 받음. lock을 안 바꿈. → CI/재현용.

npm의 `npm install`(lock 갱신) vs `npm ci`(lock 그대로 재현)와 같은 관계다.

### 3.5 배포 전 검증 명령

```bash
helm dependency list helm_charts/airflow      # 의존성 상태 확인
helm template airflow helm_charts/airflow \    # 실제 매니페스트 렌더링 (배포 전 필수)
  -f helm_charts/airflow/values/airflow.yaml
helm lint helm_charts/airflow                  # 문법/모범사례 검사
```

`helm template`은 실제로 클러스터에 적용하지 않고 **최종 YAML이 어떻게 나오는지** 눈으로 확인하는 용도다. 배포 사고를 막는 가장 싼 보험이다.

---

## 4. ArgoCD — GitOps 배포 도구

### 4.1 GitOps란

**"Git이 곧 단일 진실 공급원(Single Source of Truth)"** 이라는 운영 철학이다.

- 원하는 상태(desired state)를 Git에 선언.
- ArgoCD가 **Git ↔ 클러스터 상태를 계속 비교(diff)**.
- 다르면 Git 기준으로 **자동 동기화(sync)**.

```
   Git Repo (원하는 상태)            Kubernetes (실제 상태)
   ┌───────────────┐                ┌───────────────┐
   │ Helm charts   │  ── ArgoCD ──▶ │ Deployments   │
   │ values.yaml   │   비교 & 동기화  │ Services ...  │
   └───────────────┘   ◀── diff ──  └───────────────┘
```

### 4.2 왜 ArgoCD를 쓰는가 (장점)

1. **선언적 배포**: 배포 = Git에 PR 머지. 누가/언제/무엇을 바꿨는지 Git 히스토리로 추적.
2. **자동 드리프트 교정(self-heal)**: 누가 클러스터를 수동으로 손대도 Git 기준으로 되돌림.
3. **자동 정리(prune)**: Git에서 리소스를 지우면 클러스터에서도 삭제.
4. **시각화 UI**: 앱별 동기화 상태/헬스/리소스 트리를 한눈에.
5. **롤백**: 이전 Git 커밋으로 되돌리면 끝.

### 4.3 Application — ArgoCD의 핵심 단위

ArgoCD에서 배포 단위는 `Application`이라는 CRD다. "어떤 Git 경로/차트를, 어느 클러스터/네임스페이스에, 어떻게 동기화할지"를 정의한다.

이 레포의 Airflow `Application`(`helm_charts/argocd/apps/airflow.yaml`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: airflow
  namespace: argocd
  finalizers:
    - resources-finalizer.argocd.argoproj.io   # App 삭제 시 자식 리소스도 cascade 삭제
  annotations:
    argocd.argoproj.io/sync-wave: "2"          # 동기화 순서 제어
spec:
  project: default
  destination:
    server: https://kubernetes.default.svc     # 배포 대상 클러스터
    namespace: airflow                          # 배포 대상 네임스페이스
  sources:
    - repoURL: https://github.com/WonYong-Jang/airflow-pipeline.git
      targetRevision: main
      path: helm_charts/airflow                 # wrapper chart 경로
      helm:
        valueFiles:
          - values/airflow.yaml
  syncPolicy:
    automated: { prune: true, selfHeal: true }
    syncOptions: [CreateNamespace=true]
```

주요 필드:

- **`source`/`sources`**: 무엇을 배포할지(Git repo + path 또는 Helm repo + chart).
- **`destination`**: 어디에 배포할지(클러스터 + 네임스페이스).
- **`syncPolicy.automated`**:
  - `prune: true` → Git에서 사라진 리소스 자동 삭제.
  - `selfHeal: true` → 수동 변경 시 Git 기준으로 자동 복구.
- **`syncOptions: [CreateNamespace=true]`** → 네임스페이스 없으면 만들어줌.
- **`finalizers`** → App을 지울 때 하위 리소스까지 **cascade 삭제**.

---

## 5. Single-source vs Multi-source (★ 핵심)

ArgoCD `Application`은 소스를 **하나(`source`)** 또는 **여러 개(`sources`)** 가질 수 있다. 이 둘의 차이를 이해하는 게 이 글의 하이라이트다.

### 5.1 Single-source

소스가 하나. 보통 **wrapper chart를 내 Git에 두고 그 경로 하나만 가리키는** 형태다.

위의 Airflow 예시가 정확히 이 패턴이다. 차트(`path: helm_charts/airflow`)와 values(`values/airflow.yaml`)가 **모두 같은 Git repo 안에** 있으므로 소스 하나로 충분하다.

```
[내 Git repo]
   helm_charts/airflow/          ← wrapper chart (+ vendored tgz)
   helm_charts/airflow/values/   ← values
        ▲
        └── ArgoCD Application (source 1개)
```

- **장점**: 단순하고 직관적. 차트·값·서브차트 tgz가 모두 한 repo에 있어 재현성이 높음.
- **전제**: 서브차트 tgz를 vendoring 해둬야 ArgoCD가 외부 접근 없이 렌더링 가능.

### 5.2 Multi-source

소스가 여러 개. **"차트는 공식 Helm repo에서 직접 가져오고, values 파일은 내 Git repo에서 가져오는"** 조합에 주로 쓴다. wrapper chart를 만들지 않아도 된다.

이 레포의 VictoriaMetrics `Application`(`helm_charts/argocd/apps/victoriametrics.yaml`):

```yaml
spec:
  sources:
    - repoURL: https://github.com/WonYong-Jang/airflow-pipeline.git
      targetRevision: main
      ref: repo                                  # ① 이 소스에 "repo"라는 별칭을 붙임
    - repoURL: https://victoriametrics.github.io/helm-charts
      chart: victoria-metrics-single             # ② 공식 차트를 직접 지정
      targetRevision: 0.40.1
      helm:
        valueFiles:
          - $repo/helm_charts/victoriametrics/values/victoriametrics.yaml  # ③ ①의 별칭 참조
```

동작 원리:

1. 첫 번째 소스는 `ref: repo`로 **내 Git repo에 "repo"라는 이름표만 달아 둔다**(이 소스 자체는 차트를 배포하지 않음, 값 파일 제공용).

> **표기 메모.** `$` 뒤의 이름은 `ref`에 적은 값과 똑같이 따라간다. 여기서는 `ref: repo`라고 적었으니 `$repo`로 참조하는 것이고, **ArgoCD 공식 문서 예시는 `ref: values` → `$values`** 를 쓴다. 이름은 임의로 정할 수 있으므로 `$repo`도 유효하지만, 공식 예시를 따라가려면 `values`로 통일하는 것도 방법이다. ([Multiple Sources for an Application](https://argo-cd.readthedocs.io/en/latest/user-guide/multiple_sources/))
2. 두 번째 소스가 **실제 차트** — VictoriaMetrics 공식 Helm repo의 `victoria-metrics-single` 0.40.1.
3. 그 차트에 주입할 values 파일을 `$repo/...` 로 참조 → **①에서 붙인 별칭으로 내 repo의 values 파일을 끌어온다**.

```
[공식 Helm repo]  victoria-metrics-single:0.40.1   ← 차트(템플릿)
[내 Git repo]     .../victoriametrics.yaml          ← values  (ref: repo, $repo 로 참조)
        ▲
        └── ArgoCD Application (sources 2개를 조합)
```

### 5.3 언제 무엇을 쓰나

| | Single-source (wrapper) | Multi-source (`$ref`) |
|---|---|---|
| **차트 위치** | 내 repo (vendored tgz) | 공식 Helm repo에서 직접 |
| **wrapper chart 필요?** | 필요 | 불필요 |
| **values 위치** | 내 repo | 내 repo (`$repo`로 참조) |
| **재현성** | 매우 높음(tgz 고정) | repo가 죽으면 영향 받음 |
| **버전 업** | `helm dependency update` 후 커밋 | `targetRevision`만 수정 |
| **적합한 경우** | 커스터마이즈/서브차트 추가가 필요할 때 | 공식 차트를 값만 바꿔 쓸 때 (가벼움) |

> 정리: **Airflow처럼 손댈 게 많고 재현성이 중요하면 wrapper + vendored tgz(single-source)**, **VictoriaMetrics처럼 공식 차트를 값만 바꿔 쓰면 multi-source**가 깔끔하다. 이 레포는 두 방식을 용도에 맞게 섞어 쓴 좋은 예다.

---

## 6. App-of-Apps 패턴

`Application`이 많아지면 그걸 일일이 `kubectl apply` 하기 번거롭다. **"Application들을 배포하는 Application"** 을 하나 두는 게 App-of-Apps 패턴이다.

이 레포의 root(`helm_charts/argocd/root-app.yaml`):

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: root
  namespace: argocd
spec:
  source:
    repoURL: https://github.com/WonYong-Jang/airflow-pipeline.git
    targetRevision: main
    path: helm_charts/argocd/apps          # ← Application YAML들이 모여 있는 폴더
  destination:
    server: https://kubernetes.default.svc
    namespace: argocd
  syncPolicy:
    automated: { prune: true, selfHeal: true }
```

- `root` App이 `helm_charts/argocd/apps` 폴더를 본다.
- 그 폴더 안의 `airflow.yaml`, `victoriametrics.yaml`, `vmagent.yaml` 같은 **자식 Application들을 자동으로 생성·동기화**한다.

```
root (App-of-Apps)
 └── helm_charts/argocd/apps/
      ├── airflow.yaml          → airflow App         (Airflow 스택)
      ├── victoriametrics.yaml  → victoriametrics App  (메트릭 저장소)
      └── vmagent.yaml          → vmagent App          (메트릭 수집기)
```

→ **root App 하나만 등록(bootstrap)하면 나머지가 줄줄이 따라온다.** 새 앱을 추가하려면 `apps/` 폴더에 YAML 하나 커밋하면 끝.

---

## 7. Sync Wave — 배포 순서 제어

여러 앱/리소스를 동기화할 때 **순서**가 중요할 때가 있다. 예: 메트릭 저장소(VictoriaMetrics)가 먼저 떠야 수집기(vmagent)가 보낼 곳이 생긴다.

`argocd.argoproj.io/sync-wave` 어노테이션의 **숫자가 작을수록 먼저** 배포된다.

이 레포의 wave 설정:

| App | sync-wave | 의미 |
|-----|-----------|------|
| victoriametrics | `"0"` | 가장 먼저 (메트릭 저장소) |
| (vmagent) | (그 다음) | 저장소가 준비된 뒤 수집기 |
| airflow | `"2"` | 마지막 (실제 워크로드) |

```yaml
metadata:
  annotations:
    argocd.argoproj.io/sync-wave: "0"   # victoriametrics → 먼저
# ...
    argocd.argoproj.io/sync-wave: "2"   # airflow → 나중
```

> 의존 관계가 있는 컴포넌트는 sync-wave로 "먼저 떠야 하는 것"을 앞 번호로 지정하면 동기화 실패/재시도를 줄일 수 있다.

---

## 8. 자주 쓰는 옵션 빠른 정리

| 옵션 | 위치 | 역할 |
|------|------|------|
| `automated.prune` | syncPolicy | Git에서 지운 리소스 클러스터에서도 삭제 |
| `automated.selfHeal` | syncPolicy | 수동 변경을 Git 기준으로 자동 복구 |
| `CreateNamespace=true` | syncOptions | 대상 네임스페이스 자동 생성 |
| `resources-finalizer.argocd.argoproj.io` | finalizers | App 삭제 시 자식 리소스 cascade 삭제 |
| `sync-wave` | annotations | 동기화 순서(작을수록 먼저) |
| `ref` / `$repo` | sources | multi-source에서 다른 소스(주로 values repo) 참조 |

---

## 9. 전체 그림 한 장 요약

```
                         ┌──────────────────────────────┐
                         │  Git Repo (Single Source of   │
                         │           Truth)              │
                         │                               │
                         │  helm_charts/argocd/          │
                         │    root-app.yaml ────────────┐│
                         │    apps/*.yaml                ││
                         │  helm_charts/airflow/         ││
                         │    Chart.yaml + charts/*.tgz  ││  (wrapper + vendored)
                         │    values/airflow.yaml        ││
                         │  helm_charts/victoriametrics/ ││
                         │    values/*.yaml              ││  (multi-source용 values)
                         └──────────────┬────────────────┘
                                        │ watch & diff
                                        ▼
                              ┌───────────────────┐
                              │      ArgoCD        │
                              │  root App          │
                              │   ├─ airflow       │  single-source (wrapper)
                              │   ├─ victoriametrics│ multi-source ($repo + 공식차트)
                              │   └─ vmagent       │  multi-source
                              └─────────┬─────────┘
                                        │ sync (wave 0 → 2)
                                        ▼
                              ┌───────────────────┐
                              │    Kubernetes     │
                              │  monitoring / airflow ns │
                              └───────────────────┘
```

### 핵심 정리

- **Helm** = 템플릿 + 값으로 K8s 매니페스트를 찍어내는 패키지 매니저.
- **Wrapper chart** = 공식 차트를 의존성으로 감싸 내 repo에서 관리. **vendored tgz**로 재현성 확보.
- **`dependency update`(lock 갱신) vs `build`(lock 재현)** 를 구분.
- **ArgoCD** = Git을 진실로 삼아 클러스터를 자동 동기화하는 GitOps 도구.
- **Single-source** = 내 repo의 wrapper chart 하나. **Multi-source** = 공식 차트 + `$repo`로 참조한 내 values 조합.
- **App-of-Apps** = root App 하나로 여러 App을 부트스트랩.
- **Sync-wave** = 배포 순서 제어(작을수록 먼저).

---

## 부록 — 용어 공식성 정리

이 글에 나온 용어들이 공식 문서 표현인지, 통용어인지 구분해 둔다.

| 용어 | 구분 | 비고 |
|------|------|------|
| Multiple Sources / multi-source | ✅ 공식 (ArgoCD) | 공식 문서 페이지 제목이 "Multiple Sources for an Application" |
| `ref` / `$values` 변수 | ✅ 공식 (ArgoCD) | 공식 예시는 `ref: values` → `$values` |
| App of Apps | ✅ 공식 (ArgoCD) | 공식 섹션 제목 "App Of Apps Pattern" |
| Sync Wave (`sync-wave`) | ✅ 공식 (ArgoCD) | 어노테이션 `argocd.argoproj.io/sync-wave` |
| Umbrella chart | ✅ 공식 (Helm) | Helm 문서의 정식 명칭 |
| Subchart | ✅ 공식 (Helm) | — |
| Vendoring / vendored | 🟡 통용어 | Helm 블로그·문서에서 사용되나 공식 용어집 정의어는 아님 |
| Wrapper chart | 🟡 통용어 | 공식 명칭은 *umbrella chart* |
| Single-source | 🟡 비공식 | multi-source와 대비하기 위한 일반 표현(기본값) |
| `$repo` (이 레포 설정) | 🟡 임의 이름 | `ref: repo`로 정했기 때문. 공식 예시는 `values` 사용 |
```
