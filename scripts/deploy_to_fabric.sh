#!/bin/bash

# Fabric Cost Analysis Deployment Script
# Deploys configured notebooks to Microsoft Fabric workspace

set -e

ENVIRONMENT=$1
ARTIFACT_PATH=$2

if [ -z "$ENVIRONMENT" ] || [ -z "$ARTIFACT_PATH" ]; then
    echo "Usage: $0 <environment> <artifact-path>"
    echo "Example: $0 dev /path/to/artifacts"
    exit 1
fi

echo "🚀 Deploying FCA to $ENVIRONMENT environment"
echo "============================================="

# Set up Fabric CLI authentication
export FAB_TOKEN=$(az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv)

if [ -z "$FAB_TOKEN" ]; then
    echo "❌ Failed to get Fabric authentication token"
    exit 1
fi

echo "✅ Fabric authentication configured"

# Get workspace name based on environment
case $ENVIRONMENT in
    dev)
        WORKSPACE_NAME=${DEV_WORKSPACE_NAME:-"FCA-Development"}
        ;;
    test)
        WORKSPACE_NAME=${TEST_WORKSPACE_NAME:-"FCA-Test"}
        ;;
    prod)
        WORKSPACE_NAME=${PROD_WORKSPACE_NAME:-"FCA-Production"}
        ;;
    *)
        echo "❌ Invalid environment: $ENVIRONMENT"
        exit 1
        ;;
esac

echo "📍 Target workspace: $WORKSPACE_NAME"

# Find notebooks directory
NOTEBOOKS_DIR="$ARTIFACT_PATH/notebooks"
if [ ! -d "$NOTEBOOKS_DIR" ]; then
    NOTEBOOKS_DIR="$ARTIFACT_PATH"
fi

if [ ! -d "$NOTEBOOKS_DIR" ]; then
    echo "❌ Notebooks directory not found: $NOTEBOOKS_DIR"
    exit 1
fi

echo "📁 Notebooks directory: $NOTEBOOKS_DIR"

# Deploy notebooks
DEPLOYED_COUNT=0
TOTAL_COUNT=0

echo ""
echo "📚 Deploying notebooks..."
echo "------------------------"

for notebook in "$NOTEBOOKS_DIR"/*.ipynb; do
    if [ -f "$notebook" ]; then
        notebook_name=$(basename "$notebook" .ipynb)
        
        # Add environment suffix for non-production deployments
        if [ "$ENVIRONMENT" != "prod" ]; then
            target_name="${notebook_name}_$(echo $ENVIRONMENT | tr '[:lower:]' '[:upper:]')"
        else
            target_name="$notebook_name"
        fi
        
        echo "  📖 Deploying: $notebook_name → $target_name"
        
        # Deploy notebook using Fabric CLI
        if fab import "/$WORKSPACE_NAME.Workspace/$target_name" -i "$notebook" -f --format .ipynb; then
            echo "    ✅ Successfully deployed: $target_name"
            ((DEPLOYED_COUNT++))
        else
            echo "    ❌ Failed to deploy: $target_name"
        fi
        
        ((TOTAL_COUNT++))
    fi
done

# Deploy additional artifacts if they exist
echo ""
echo "🔧 Deploying additional artifacts..."
echo "-----------------------------------"

# Deploy lakehouse definitions if they exist
LAKEHOUSE_DIR="$ARTIFACT_PATH/lakehouses"
if [ -d "$LAKEHOUSE_DIR" ]; then
    for lakehouse in "$LAKEHOUSE_DIR"/*; do
        if [ -d "$lakehouse" ]; then
            lakehouse_name=$(basename "$lakehouse")
            
            if [ "$ENVIRONMENT" != "prod" ]; then
                target_name="${lakehouse_name}_$(echo $ENVIRONMENT | tr '[:lower:]' '[:upper:]')"
            else
                target_name="$lakehouse_name"
            fi
            
            echo "  🏠 Creating lakehouse: $target_name"
            
            if fab create "/$WORKSPACE_NAME.Workspace/$target_name"; then
                echo "    ✅ Successfully created lakehouse: $target_name"
            else
                echo "    ⚠️  Lakehouse may already exist: $target_name"
            fi
        fi
    done
fi

# Deploy semantic models if they exist
SEMANTIC_MODEL_DIR="$ARTIFACT_PATH/semantic-models"
if [ -d "$SEMANTIC_MODEL_DIR" ]; then
    for model in "$SEMANTIC_MODEL_DIR"/*; do
        if [ -d "$model" ]; then
            model_name=$(basename "$model")
            
            if [ "$ENVIRONMENT" != "prod" ]; then
                target_name="${model_name}_$(echo $ENVIRONMENT | tr '[:lower:]' '[:upper:]')"
            else
                target_name="$model_name"
            fi
            
            echo "  📊 Deploying semantic model: $target_name"
            
            if fab import "/$WORKSPACE_NAME.Workspace/$target_name" -i "$model" -f; then
                echo "    ✅ Successfully deployed semantic model: $target_name"
            else
                echo "    ❌ Failed to deploy semantic model: $target_name"
            fi
        fi
    done
fi

# Deploy reports if they exist  
REPORTS_DIR="$ARTIFACT_PATH/reports"
if [ -d "$REPORTS_DIR" ]; then
    for report in "$REPORTS_DIR"/*; do
        if [ -d "$report" ]; then
            report_name=$(basename "$report")
            
            if [ "$ENVIRONMENT" != "prod" ]; then
                target_name="${report_name}_$(echo $ENVIRONMENT | tr '[:lower:]' '[:upper:]')"
            else
                target_name="$report_name"
            fi
            
            echo "  📈 Deploying report: $target_name"
            
            if fab import "/$WORKSPACE_NAME.Workspace/$target_name" -i "$report" -f; then
                echo "    ✅ Successfully deployed report: $target_name"
            else
                echo "    ❌ Failed to deploy report: $target_name"
            fi
        fi
    done
fi

echo ""
echo "📊 Deployment Summary"
echo "==================="
echo "Environment: $ENVIRONMENT"
echo "Workspace: $WORKSPACE_NAME"
echo "Notebooks deployed: $DEPLOYED_COUNT/$TOTAL_COUNT"

if [ $DEPLOYED_COUNT -eq $TOTAL_COUNT ] && [ $TOTAL_COUNT -gt 0 ]; then
    echo "✅ All deployments completed successfully!"
    exit 0
else
    echo "⚠️  Some deployments may have failed. Check logs above."
    exit 1
fi