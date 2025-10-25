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

# Try config-based deployment first (experimental features)
echo ""
echo "🧪 Attempting config-based deployment..."
echo "======================================="

if python3 scripts/deploy_fabric_items.py --environment "$ENVIRONMENT" --config-file fabric-config.yml --install-deps; then
    echo "✅ Config-based deployment completed successfully!"
    exit 0
fi

echo ""
echo "⚠️  Config-based deployment failed, trying basic deployment..."
echo "============================================================="

# Fallback to basic individual item deployment  
if python3 scripts/deploy_fabric_items_basic.py --environment "$ENVIRONMENT" --install-deps; then
    echo "✅ Basic deployment completed successfully!"
    exit 0
fi

echo ""
echo "❌ Both deployment methods failed!"
echo "================================="
echo ""
echo "Troubleshooting steps:"
echo "1. Check that fabric-cicd library supports your configuration"
echo "2. Verify workspace IDs are correct in fabric-config.yml"
echo "3. Ensure Service Principal has proper permissions"
echo "4. Check experimental features are enabled in fabric-cicd"
echo ""

exit 1