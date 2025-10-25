#!/bin/bash

# Microsoft Fabric CI/CD Deployment Script
# Deploys Fabric items using fabric-cicd library with fallback support

set -e

ENVIRONMENT=$1
ARTIFACT_PATH=$2

if [ -z "$ENVIRONMENT" ] || [ -z "$ARTIFACT_PATH" ]; then
    echo "Usage: $0 <environment> <artifact-path>"
    echo "Example: $0 dev /path/to/artifacts"
    exit 1
fi

echo "🚀 Deploying to Microsoft Fabric $ENVIRONMENT environment"
echo "========================================================="

# Change to the artifact directory to find config files
cd "$ARTIFACT_PATH"

echo "📁 Working directory: $(pwd)"
echo "� Available files:"
ls -la

# Try enhanced deployment with automatic fallback
echo ""
echo "🚀 Starting enhanced deployment with automatic fallback..."
echo "=========================================================="

if python3 scripts/deploy_fabric_items.py --environment "$ENVIRONMENT" --config-file fabric-config.yml --install-deps; then
    echo "✅ Deployment completed successfully!"
    exit 0
fi

echo ""
echo "⚠️  Enhanced deployment failed, trying standard approach..."
echo "==========================================================="

# Fallback to standard fabric-cicd approach
if python3 scripts/deploy_fabric_items_standard.py --environment "$ENVIRONMENT" --install-deps; then
    echo "✅ Standard deployment completed successfully!"
    exit 0
fi

echo ""
echo "❌ All deployment methods failed!"
echo "================================="
echo ""
echo "Troubleshooting steps:"
echo "1. Check that fabric-cicd library is properly installed"
echo "2. Verify workspace IDs are correct in fabric-config.yml"
echo "3. Ensure Service Principal has proper permissions"
echo "4. Check repository structure matches expected format"
echo "5. Verify authentication credentials are valid"
echo ""

exit 1