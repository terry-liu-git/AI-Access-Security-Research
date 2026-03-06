# AI Agent Access Security Research Benchmark: Customizing DoomArena in OSWorld to Monitor Unauthorized Access

**Author:** Xuanlin “Terry” Liu (xliu91@stevens.edu)  
**Affiliation:** Stevens Institute for Artificial Intelligence (Lab), Stevens Institute of Technology

This repository is a customized DoomArena + OSWorld environment in research of exploring **AI agent access security** in desktop environments while completing various tasks.  
It extends the default setups of DoomArena + OSWorld with **protected-resource policies** (paths, URLs, literals, regex) and **runtime monitoring** to measure whether an agent accesses or exposes protected data during task execution.

## Scope

- Benchmark evaluation across default OSWorld tasks
- Contextual protected-resource policies per task
- Monitoring of:
  - interaction actions
  - environment/context access signals
  - model response output

> Note: The monitor is measurement instrumentation, not a hard blocking firewall.

## Current Setup

- **Model tested:** GPT-4o
- **Observation mode:** VM monitor recording, screenshot, action trajectory logs
- **Primary output artifact per episode:** `protected_monitor.jsonl`

## Snapshot Results (Runs 1–3, Mar 2026)

- 1,080 total episodes analyzed
- 4 violation episodes detected (0.37%)
- 4 violating steps out of 13,599 logged steps (0.03%)
- Detected violations were response-output regex matches (email pattern).

<img src="quick_result_summaries/runs_1_to_3_overview.png" alt="Runs 1-3 Overview" width="50%" />

Results (by runs 1-3, Mar 2026) suggest low observed protected-resource leakage under current benchmark configuration.  


# Latest Runs:

## Latest Run [March 6, 2026] (Run 3)

- Model tested: `gpt-4o`
- Episodes analyzed: `360` total, `359` with `protected_monitor.jsonl`
- Violations: `1` episode (`0.28%`) and `1` step (`0.02%` of logged steps)
- Detected pattern: `(?i)^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$` in `response_output`
- Modifications (vs. previous run): benchmark regenerated with stronger task-context dependency for protected resources to increase likelihood of an agent encountering contextualized protected resources.

## Historical Runs

| Run | Date | Episodes (monitored) | Violation Episodes | Violation Steps | Modifications |
| --- | --- | --- | --- | --- | --- |
| Run 1 | March 4, 2026 | `360` (`359`) | `0` | `0` | Baseline protected benchmark |
| Run 2 | March 5, 2026 | `360` (`359`) | `3` | `3` | Switched from generic `protected-scenario-*` to contextual `contextual-*` task policies |
| Run 3 | March 6, 2026 | `360` (`359`) | `1` | `1` | Increased task-context dependency of protected resources in benchmark generation |

## Detailed Reports

- Run 1: [quick_result_summaries/run_one/protected_resources_full_rerun_20260302_report.md](quick_result_summaries/run_one/protected_resources_full_rerun_20260302_report.md) | [quick_result_summaries/run_one/protected_resources_full_rerun_20260302_report.json](quick_result_summaries/run_one/protected_resources_full_rerun_20260302_report.json)
- Run 2: [quick_result_summaries/run_two/protected_resources_second_run_20260304_report.md](quick_result_summaries/run_two/protected_resources_second_run_20260304_report.md) | [quick_result_summaries/run_two/protected_resources_second_run_20260304_report.json](quick_result_summaries/run_two/protected_resources_second_run_20260304_report.json)
- Run 3: [quick_result_summaries/run_three/protected_resources_third_run_20260305_report.md](quick_result_summaries/run_three/protected_resources_third_run_20260305_report.md) | [quick_result_summaries/run_three/protected_resources_third_run_20260305_report.json](quick_result_summaries/run_three/protected_resources_third_run_20260305_report.json)
- Overview chart: [quick_result_summaries/runs_1_to_3_overview.png](quick_result_summaries/runs_1_to_3_overview.png)


## The following is the original information on the DoomArena platform:


# DoomArena: A Framework for Testing AI Agents Against Evolving Security Threats

<a href='https://arxiv.org/abs/2504.14064'><img src="https://img.shields.io/badge/Arxiv-2504.14064-A42C25?style=flat&logo=arXiv&logoColor=A42C25"></img></a>
[![pypi](https://badge.fury.io/py/doomarena.svg)](https://pypi.org/project/doomarena/)
[![PyPI - License](https://img.shields.io/pypi/l/doomarena?style=flat-square)]([https://opensource.org/licenses/MIT](http://www.apache.org/licenses/LICENSE-2.0))
[![PyPI - Downloads](https://img.shields.io/pypi/dm/doomarena?style=flat-square)](https://pypistats.org/packages/doomarena)
[![GitHub star chart](https://img.shields.io/github/stars/ServiceNow/DoomArena?style=flat-square)](https://star-history.com/#ServiceNow/DoomArena)

<img src="https://raw.githubusercontent.com/ServiceNow/DoomArena/gh_pages/static/images/doomarena_indiana_jones.jpg" width="320"></img>

[DoomArena](https://servicenow.github.io/DoomArena/) is a modular, configurable, plug-in security testing framework for AI agents that supports many agentic frameworks including [$\tau$-bench](https://github.com/sierra-research/tau-bench), [Browsergym](https://github.com/ServiceNow/browsergym), [OSWorld](https://github.com/xlang-ai/OSWorld) and [TapeAgents](https://github.com/ServiceNow/tapeagents) (see Mail agent example). It enables testing agents in the face of adversarial attacks consistent with a given threat model, and supports several attacks (with the ability for users to add their own) and several threat models. 


## 🚀 Quick Start

The [DoomArena Intro Notebook](https://colab.research.google.com/github/ServiceNow/DoomArena/blob/master/notebooks/doomarena_intro_notebook.ipynb)
is a good place for learning hands-on about the core concepts of DoomArena.
You will implement an `AttackGateway` and a simple `FixedInjectionAttack` to alter the normal behavior of a simple flight searcher agent.

If you only want to use the library just run
```bash
pip install doomarena  # core library, minimal dependencies
```

If you want to run DoomArena integrated with [TauBench](https://github.com/sierra-research/tau-bench/), additionally run

```bash
pip install doomarena-taubench  # optional
```

If you want to run DoomArena integrated with [Browsergym](https://github.com/ServiceNow/BrowserGym), additionally run

```bash
pip install doomarena-browsergym  # optional
```

If you want to test attacks on a Mail Agent (which can summarize and send emails on your behalf) inspired by the [LLMail Challenge](https://llmailinject.azurewebsites.net/) run
```bash
pip install -e doomarena/mailinject  # optional
```

If you want to run DoomArena integrated with [OSWorld](https://github.com/xlang-ai/OSWorld) run
```
pip install -e doomarena/osworld
```
and follow our setup instructions [here](doomarena/osworld/README.md).


Export relevant API keys into your environment or `.env` file.
```bash
OPENAI_API_KEY="<your api key>"
OPENROUTER_API_KEY="<your api key>"
```

## 🛠️ Advanced Setup

To actively develop `DoomArena`, please create a virtual environment and install the package locally in editable mode using
```bash
pip install -e doomarena/core
pip install -e doomarena/taubench
pip install -e doomarena/browsergym
pip install -e doomarena/mailinject
pip install -e doomarena/osworld
```

Once the environments are set up, run the tests to make sure everything is working.
```bash
make ci-tests
make tests
```


## 💻 Running Experiments

Follow the environment-specific instructions for [TauBench](doomarena/taubench/README.md) and [BrowserGym](doomarena/browsergym/README.md)

## 🌟 Contributors

[![DoomArena contributors](https://contrib.rocks/image?repo=ServiceNow/doomarena&max=2000)](https://github.com/ServiceNow/DoomArena/graphs/contributors)

Note: contributions made prior to the open-sourcing are not accounted for; please refer to author list for full list of contributors.

## 📝 Paper

If you found DoomArena helpful, please cite us
```
@misc{boisvert2025doomarenaframeworktestingai,
      title={DoomArena: A framework for Testing AI Agents Against Evolving Security Threats}, 
      author={Leo Boisvert and Mihir Bansal and Chandra Kiran Reddy Evuru and Gabriel Huang and Abhay Puri and Avinandan Bose and Maryam Fazel and Quentin Cappart and Jason Stanley and Alexandre Lacoste and Alexandre Drouin and Krishnamurthy Dvijotham},
      year={2025},
      eprint={2504.14064},
      archivePrefix={arXiv},
      primaryClass={cs.CR},
      url={https://arxiv.org/abs/2504.14064}, 
}
```
