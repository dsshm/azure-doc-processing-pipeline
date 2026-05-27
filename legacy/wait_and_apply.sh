#!/bin/bash
set -e

echo "Checking if CAE is still being deleted..."
while true; do
  STATE=$(az containerapp env show --name cae-docpipeline-dev-nnsn8a --resource-group rg-docpipeline-dev-nnsn8a --query "properties.provisioningState" -o tsv 2>/dev/null || echo "NotFound")
  if [ "$STATE" = "ScheduledForDelete" ]; then
    echo "Still deleting... $(date +%H:%M:%S)"
    sleep 15
  else
    echo "CAE state: $STATE - proceeding with apply"
    break
  fi
done

echo "Running terraform apply..."
terraform -chdir=terraform apply -auto-approve
