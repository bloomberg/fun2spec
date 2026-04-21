# fun2spec

## ℹ️ About

fun2spec is a new tool used to automatically infer code contracts for large C++ libraries.

In particular, fun2spec uses large language models (LLMs) to generate postcondition specifications for C++ functions.

Two case studies are presented: BDE (the Bloomberg Development Environment library) and BlazingMQ (an open source message queue solution developed at Bloomberg).

These projects contain several millions of lines of code and constitute great experiments showcasing what can be done with fun2spec.

We have documented fun2spec experiments in our paper: [Fun2spec: Code Contract Synthesis At Scale](fun2spec_FSE2026.pdf), which has been accepted for publication at [FSE 2026](https://conf.researchr.org/track/fse-2026/fse-2026-industry-papers) in July.

## :bulb: Installation

### BDE Installations
To use fun2spec with Bloomberg's BDE codebase, the BDE CMake build system requires the following software to be preinstalled and configured on the system:

* [CMake](https://cmake.org) version 3.24 or later
* [Ninja](https://ninja-build.org/) (recommended) or GNU Make
* [Python](https://www.python.org/)

Clone the `bde-tools` and `bde` repositories and add `bde-tools` to your `PATH`:
  ```shell
   $ git clone https://github.com/bloomberg/bde-tools.git
   $ export PATH=$PWD/bde-tools/bin:$PATH      # add bde-tools to the 'PATH'
   $ git clone https://github.com/bloomberg/bde.git
   ```
Please see the complete [build instructions for open source users](https://bloomberg.github.io/bde/library_information/build.html).
   
### Python Installation and Usage Instructions
We recommend creating a new conda/pipenv environment for installing the dependencies.

<details>
  <summary>Click here for steps to set up a conda environment</summary>
Instructions for installing miniconda in your machine are <a href="https://docs.anaconda.com/free/miniconda/miniconda-install/">here</a>.
  
```
conda create -n venv_name
conda activate venv_name
conda install pip
```
  
</details>

To install all the requirements for fun2spec:

```
pip install -r requirements.txt
```

To run the tool with CLI, run `fun2spec/main.py` with the following arguments:
| Argument     | Type  |  Description  |
  | ------------- |-----  |  ----- |
  | `source`   | str   | Path to the C++ repository humaneval, fsc or paths to BDE and BlazingMQ |
  | `model_name`       | str   | Hugging Face model ID; defaults to **microsoft/Phi-3-mini-128k-instruct** |
  | `gen_name`   | str   | fun2spec or daikon. Defaults to fun2spec |
  | `return_type` | str  | The generation is performed on functions with provided return type; currently support **int**, **pointer** or **all** |
  | `use_cache`   | bool  | If there are changes in the fun2spec or the repository to be analyzed, set use_cache to False. Defaults to True. |
  | `count`       | int  | Number of functions for which the specifications are generated. Defaults to 50. |
  | `timeout`     | int  | Timeout in seconds for each function. Defaults to 30s |

For example, you can run the following command to run fun2spec on a BDE repository given `~/bde` is the local path to the clone of the repository.
```
python3 fun2spec/main.py --source ~/bde  --return_type pointer --count 30 --use_cache True
```

### :page_facing_up: Results
Execution of fun2spec should generate a file `data/results.csv`. The CSV contains the following columns:
| Column Name        | Description  |
  | ------------- |-----|
  | `Function Name`     | The function name that is tested. |
  | `Postcondition`     | LLM generated postcondition. |
  | `true`     |   Count of executions of function where the postcondition holds. |
  | `false`     | Count of executions of function where the postcondition does not hold. |
