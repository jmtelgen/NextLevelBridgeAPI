# Deployment Script Update Memory

## Always Update deploy-aws.sh for New Lambda Functions

When creating new Lambda functions, always update the `deploy-aws.sh` script to include:

### Required Updates:

1. **Help Text** (lines 14-35): Add function to available functions list
2. **Case Mapping** (lines 44-104): Add case statement mapping function name to Lambda name
3. **Environment Variables** (lines 105-132): Add environment variables configuration
4. **Timeout/Memory Settings** (lines 138-147): Add function-specific timeout and memory settings
5. **Next Steps Guidance** (lines 179-193): Add deployment-specific next steps

### Example for New Function:
```bash
# In help text
echo "  my-new-function → MyNewFunctionLambda"

# In case mapping
"my-new-function")
    LAMBDA_FUNCTION_NAME="MyNewFunctionLambda"
    ;;

# In environment variables
elif [[ $FUNCTION_NAME == my-new-function ]]; then
    ENV_VARS="Variables={MY_VAR=my-value}"

# In timeout/memory (if needed)
elif [[ $FUNCTION_NAME == my-new-function ]]; then
    FUNCTION_TIMEOUT=60
    FUNCTION_MEMORY=1024

# In next steps (if needed)
elif [[ $FUNCTION_NAME == my-new-function ]]; then
    echo "1. Configure specific setup for my-new-function"
    echo "2. Test the function"
```

This ensures all new Lambda functions can be deployed consistently using the automated deployment script.
