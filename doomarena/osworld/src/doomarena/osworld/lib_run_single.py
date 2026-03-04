import datetime
import json
import logging
import os
import time
from wrapt_timeout_decorator import *
from typing import Optional
from doomarena.osworld.protected_monitor import ProtectedResourceMonitor

logger = logging.getLogger("desktopenv.experiment")


def run_single_example(
    agent, env, example, max_steps, instruction, args, example_result_dir, scores, protected_monitor: Optional[ProtectedResourceMonitor] = None, domain: str = "unknown", example_id: str = "unknown",
):
    runtime_logger = setup_logger(example, example_result_dir)
    agent.reset(runtime_logger)
    env.reset(task_config=example)
    time.sleep(15)  # Wait for the environment to be ready
    obs = env._get_obs()  # Get the initial observation
    done = False
    step_idx = 0
    env.controller.start_recording()
    while not done and step_idx < max_steps:
        response, actions = agent.predict(instruction, obs)
        reward = 0.0
        info = {}
        action_timestamp = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
        last_action = None
        for action in actions:
            # Capture the timestamp before executing the action
            action_timestamp = datetime.datetime.now().strftime("%Y%m%d@%H%M%S")
            logger.info("Step %d: %s", step_idx + 1, action)
            obs, reward, done, info = env.step(action, args.sleep_after_execution)
            last_action = action
        if not actions:
            logger.warning("No actions produced at step %d; ending episode early.", step_idx + 1)
            done = True
        if protected_monitor is not None:
            protected_monitor.observe_step(
                domain=domain,
                example_id=example_id,
                step_num=step_idx + 1,
                action=actions,
                info=info,
                response=response,
                obs=obs,
                when="after_step",
            )
        logger.info("Reward: %.2f", reward)
        logger.info("Done: %s", done)
        with open(
            os.path.join(
                example_result_dir, f"step_{step_idx + 1}_{action_timestamp}.png"
            ),
            "wb",
        ) as _f:
            _f.write(obs["screenshot"])
        with open(os.path.join(example_result_dir, "traj.jsonl"), "a") as f:
            f.write(
                json.dumps(
                    {
                        "step_num": step_idx + 1,
                        "action_timestamp": action_timestamp,
                        "action": last_action,
                        "actions": actions,
                        "response": response,
                        "reward": reward,
                        "done": done,
                        "info": info,
                        "screenshot_file": f"step_{step_idx + 1}_{action_timestamp}.png",
                    }
                )
            )
            f.write("\n")
        if done:
            logger.info("The episode is done.")
            break
        step_idx += 1
    result = env.evaluate()
    logger.info("Result: %.2f", result)
    scores.append(result)
    with open(
        os.path.join(example_result_dir, "result.txt"), "w", encoding="utf-8"
    ) as f:
        f.write(f"{result}\n")
    env.controller.end_recording(os.path.join(example_result_dir, "recording.mp4"))


def setup_logger(example, example_result_dir):
    runtime_logger = logging.getLogger(f"desktopenv.example.{example['id']}")
    runtime_logger.setLevel(logging.DEBUG)
    runtime_logger.addHandler(
        logging.FileHandler(os.path.join(example_result_dir, "runtime.log"))
    )
    return runtime_logger
