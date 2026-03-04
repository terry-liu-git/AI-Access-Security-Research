# AI Agent Access Security Research

Conducted by Xuanlin "Terry" Liu (xliu91@stevens.edu), collaborating with professor William Eiers, Zining Zhu

Customized DoomArena integrated into OSWorld test environments to arbitrarily select protected resources (directories, addresses, files, regular expressions) without guardrail to see if the AI agents would access, interact, or obtain protected resources. 

Currently testing with ChatGPT 4o


# Latest Runs:

## Run one [March 4, 2026]: 

Protected resource benchmark rerun analyzed from `../protected_resources_full_rerun_20260302/pyautogui/screenshot/gpt-4o`.

- Model tested: `gpt-4o`
- Total episode directories analyzed: `360`
- Episodes with `protected_monitor.jsonl`: `359`
- Episodes missing monitor data: `1` (`multi_apps/e8172110-ec08-421b-a6f5-842e6451911f`)
- Total trajectory steps: `4,360`
- Total monitored steps: `4,359`

Protected resource policy coverage in monitored episodes:

- Episodes with protected path literals: `359`
- Episodes with protected URL literals: `359`
- Episodes with protected regular expressions: `359`

Domains covered:

- `chrome` (`46`)
- `gimp` (`26`)
- `libreoffice_calc` (`47`)
- `libreoffice_impress` (`47`)
- `libreoffice_writer` (`23`)
- `multi_apps` (`93`)
- `os` (`24`)
- `thunderbird` (`15`)
- `vlc` (`17`)
- `vs_code` (`22`)

Results:

- Violation episodes: `0`
- Violation steps: `0`
- Matched protected literals: `0`
- Matched protected regex patterns: `0`
- Top matched protected patterns: none

Observed behavior:

- The benchmark logged ordinary task-related paths and URLs such as `chrome://settings`, `https://www.google.com`, `/home/user/Desktop`, and `/tmp`.
- No monitored episode showed the agent typing, quoting, navigating to, or surfacing protected directories, protected addresses, protected files, or regex-defined secret strings.
- This run indicates the protected-resource boundary held for the monitored benchmark cases.







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
