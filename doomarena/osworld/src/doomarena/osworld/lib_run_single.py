import datetime
import json
import logging
import os
import time
from wrapt_timeout_decorator import *
from typing import List, Optional
from doomarena.osworld.protected_monitor import ProtectedResourceMonitor

logger = logging.getLogger("desktopenv.experiment")


def _write_step_screenshot(obs, example_result_dir, step_num, action_timestamp):
    screenshot_filename = f"step_{step_num}_{action_timestamp}.png"
    screenshot_path = os.path.join(example_result_dir, screenshot_filename)
    screenshot_bytes = obs.get("screenshot") if isinstance(obs, dict) else None
    if not isinstance(screenshot_bytes, (bytes, bytearray)):
        logger.warning(
            "Missing/invalid screenshot bytes at step %d; got %s",
            step_num,
            type(screenshot_bytes).__name__,
        )
        return None
    with open(screenshot_path, "wb") as screenshot_file:
        screenshot_file.write(screenshot_bytes)
    return screenshot_filename


def append_episode_error_traj_entry(
    *,
    example_result_dir: str,
    error_message: str,
    domain: str,
    example_id: str,
) -> None:
    with open(os.path.join(example_result_dir, "traj.jsonl"), "a", encoding="utf-8") as f:
        f.write(
            json.dumps(
                {
                    "Error": error_message,
                    "domain": domain,
                    "example_id": example_id,
                }
            )
        )
        f.write("\n")


def write_terminal_episode_artifacts(
    *,
    example_result_dir: str,
    domain: str,
    example_id: str,
    status: str,
    result: float,
    error_message: str = "",
) -> None:
    payload = {
        "status": status,
        "result": float(result),
        "domain": domain,
        "example_id": example_id,
        "error": error_message,
        "updated_utc": datetime.datetime.now(datetime.UTC).isoformat().replace(
            "+00:00", "Z"
        ),
    }
    with open(
        os.path.join(example_result_dir, "episode_status.json"),
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    with open(
        os.path.join(example_result_dir, "result.txt"),
        "w",
        encoding="utf-8",
    ) as f:
        f.write(f"{float(result)}\n")


def run_single_example(
    agent,
    env,
    example,
    max_steps,
    instruction,
    args,
    example_result_dir,
    scores,
    protected_monitor: Optional[ProtectedResourceMonitor] = None,
    protected_monitors: Optional[List[ProtectedResourceMonitor]] = None,
    domain: str = "unknown",
    example_id: str = "unknown",
):
    runtime_logger = setup_logger(example, example_result_dir)
    agent.reset(runtime_logger)
    env.reset(task_config=example)
    time.sleep(15)  # Wait for the environment to be ready
    obs = env._get_obs()  # Get the initial observation
    done = False
    step_idx = 0
    monitors: List[ProtectedResourceMonitor] = []
    if protected_monitor is not None:
        monitors.append(protected_monitor)
    if protected_monitors:
        monitors.extend(protected_monitors)
    env.controller.start_recording()
    episode_status = "completed"
    episode_error = ""
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
        for monitor in monitors:
            monitor.observe_step(
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
        screenshot_file = _write_step_screenshot(
            obs=obs,
            example_result_dir=example_result_dir,
            step_num=step_idx + 1,
            action_timestamp=action_timestamp,
        )
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
                        "screenshot_file": screenshot_file,
                    }
                )
            )
            f.write("\n")
        if done:
            logger.info("The episode is done.")
            break
        step_idx += 1
    try:
        result = float(env.evaluate())
    except Exception as exc:
        import traceback

        logger.error(
            "Evaluation failed for %s/%s; forcing result to 0.0. Error: %s",
            domain,
            example_id,
            exc,
        )
        logger.error("Evaluation traceback: %s", traceback.format_exc())
        episode_status = "evaluation_failed"
        episode_error = f"{type(exc).__name__}: {exc}"
        result = 0.0
    logger.info("Result: %.2f", result)
    scores.append(result)
    write_terminal_episode_artifacts(
        example_result_dir=example_result_dir,
        domain=domain,
        example_id=example_id,
        status=episode_status,
        result=result,
        error_message=episode_error,
    )
    try:
        env.controller.end_recording(os.path.join(example_result_dir, "recording.mp4"))
    except Exception as exc:
        logger.error(
            "Failed to stop recording for %s/%s: %s",
            domain,
            example_id,
            exc,
        )


def setup_logger(example, example_result_dir):
    runtime_logger = logging.getLogger(f"desktopenv.example.{example['id']}")
    runtime_logger.setLevel(logging.DEBUG)
    runtime_logger.addHandler(
        logging.FileHandler(os.path.join(example_result_dir, "runtime.log"))
    )
    return runtime_logger
