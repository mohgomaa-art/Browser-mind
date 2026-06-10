"""
Usage:
  python -m pipeline.pipeline_runner --pipeline pipelines/youtube_trends.json
  python -m pipeline.pipeline_runner --pipeline pipelines/youtube_trends.json --headless false
"""
import argparse
import asyncio
import json
import time
from pathlib import Path

from core.executor import ActionExecutor
from model.agent_policy import AgentPolicy
from pipeline.orchestrator import PipelineOrchestrator

async def main():
    import sys
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    
    parser = argparse.ArgumentParser()
    parser.add_argument("--pipeline", type=str, required=True, help="Path to pipeline JSON")
    parser.add_argument("--headless", type=str, default="true", help="Run in headless mode")
    args = parser.parse_args()

    headless = args.headless.lower() == "true"
    pipeline_path = Path(args.pipeline)
    if not pipeline_path.exists():
        print(f"Error: Pipeline file {pipeline_path} not found.")
        return

    with open(pipeline_path, 'r', encoding='utf-8') as f:
        pipeline_def = json.load(f)

    print(f"Initializing BrowserMind Pipeline Runner...")
    
    # Load policy if available
    policy = None
    best_ckpt = Path("checkpoints/best.pt")
    if best_ckpt.exists():
        try:
            policy = AgentPolicy()
            policy.load_weights(str(best_ckpt))
            print("Loaded AgentPolicy weights.")
        except Exception as e:
            print(f"Warning: Could not load policy from {best_ckpt}: {e}")

    executor = ActionExecutor(policy_v2=policy)
    
    try:
        # ActionExecutor does not have initialize(). The browser starts automatically in execute_task() as seen in runner
        # Wait, no ActionExecutor doesn't have initialize()
        # let's just make the orchestrator use executor.
        orchestrator = PipelineOrchestrator(executor=executor, headless=headless)
        start_time = time.time()
        
        result = await orchestrator.run_pipeline(pipeline_def)
        
        duration = time.time() - start_time
        print(f"\n=== Pipeline Execution Summary ===")
        print(f"Success: {result['success']} in {duration:.1f}s")
        print("\n=== Final Buffer Contents ===")
        for k, v in result["buffer"].items():
            preview = v[:100].replace('\n', ' ') + "..." if len(v) > 100 else v
            print(f"[{k}]: {preview} ({len(v)} chars)")
            
        # Save results
        out_dir = Path("pipeline_results")
        out_dir.mkdir(exist_ok=True)
        ts = int(time.time())
        name = pipeline_path.stem
        out_file = out_dir / f"{ts}_{name}.json"
        
        with open(out_file, 'w', encoding='utf-8') as f:
            json.dump({
                "pipeline_name": pipeline_def.get("name", name),
                "success": result["success"],
                "duration_sec": duration,
                "history": result["history"],
                "buffer": result["buffer"]
            }, f, indent=2, ensure_ascii=False)
            
        print(f"\nSaved full results to {out_file}")
        
    finally:
        pass # executor handles its own stealth browser gracefully or we can call executor.stop() if exposed.
        # let's just do nothing, ActionExecutor.stop() might not be public or we don't hold a persistent browser.
        # Wait, the ActionExecutor has a persistent stealth browser? Actually execute_task handles start/stop normally.

if __name__ == "__main__":
    asyncio.run(main())
