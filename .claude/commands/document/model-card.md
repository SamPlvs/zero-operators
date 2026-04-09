---
description: Generate a standard model card for the project
argument-hint: <project-name>
---

# /model-card — Model Card Generator

You are generating a model card following standard practices for a Zero Operators project.

## Steps

1. **Read the project plan** (`targets/{project-name}.target.md`). Extract:
   - Objective and problem statement
   - Constraints and requirements
   - Data sources
   - Success criteria

2. **Read oracle evaluation results**. Look in:
   - `oracle/reports/` for structured results
   - DECISION_LOG.md for gate events and metric history
   - Comms JSONL logs for gate events

3. **Read model architecture from source code**. Look in:
   - `models/` directory for architecture definitions
   - Training scripts for hyperparameters
   - Experiment configs for training details

4. **Generate the model card** with these sections:

   ```markdown
   # Model Card: {project-name}
   **Generated**: {date}

   ## Model Details
   - **Architecture**: {model type, layers, key design choices}
   - **Training procedure**: {optimizer, learning rate, epochs, batch size}
   - **Hyperparameters**: {key hyperparameters and values}
   - **Framework**: PyTorch
   - **Training date**: {date of final training run}
   - **Version**: {model version or checkpoint ID}

   ## Intended Use
   - **Primary use case**: {from plan objective}
   - **Users**: {intended consumers of model output}
   - **Out-of-scope uses**: {what this model should NOT be used for}

   ## Training Data
   - **Source**: {data sources from plan}
   - **Size**: {dataset size, number of samples}
   - **Preprocessing**: {key data transformations}
   - **Splits**: {train/val/test split ratios and strategy}

   ## Evaluation Results
   - **Primary metric**: {metric name} = {value} (threshold: {threshold})
   - **Tier 1 (Core)**: {result}
   - **Tier 2 (Operational)**: {result}
   - **Tier 3 (Robustness)**: {result}
   - **Per-stratum breakdown**: {if applicable}

   ## Limitations and Biases
   - {Known failure modes from oracle evaluation}
   - {Data limitations or gaps}
   - {Distribution assumptions that may not hold}

   ## Ethical Considerations
   - {Potential misuse scenarios}
   - {Fairness considerations}
   - {Privacy implications if applicable}
   ```

5. **Write the model card** to `reports/model_card.md` in the delivery repo. Create `reports/` if needed.

6. **Report** to the user:
   - Summary of model card contents
   - Any sections that need manual review or additional information
   - Path to the generated file
