# Development Sandbox

**IMPORTANT**: This directory is for experimental work only. No production code should import from here.

## Purpose
- Test new features before production
- Prototype complex algorithms
- Debug edge cases with isolated test scripts

## Structure
- `experiments/`: One-off scripts and prototypes
- `prototypes/`: More structured experimental features
- `test_cases/`: Sample quiz files for testing edge cases

## Rules
1. Never import from `dev/` in production code
2. When code is stable, move it to appropriate production module
3. Document all experiments with README files
4. Clean up old experiments regularly
