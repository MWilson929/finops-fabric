# MasterDataManagement SQL Database

## Overview
The MasterDataManagement SQL Database serves as the central repository for reference data, lookup tables, and dimensional data supporting FinOps Hub cost analysis and reporting processes.

## Purpose
- **Reference Data**: Store standardized lookup tables and mappings
- **Dimensional Data**: Maintain business hierarchies and organizational structures  
- **Data Governance**: Centralize master data definitions and relationships
- **Cost Allocation**: Support advanced cost allocation and chargeback scenarios
- **Reporting**: Provide enriched dimensional data for FinOps reporting

## Database Structure

### Core Tables (Recommended)
```sql
-- Organizational hierarchy and cost centers
dbo.Organizations
dbo.CostCenters  
dbo.Departments
dbo.BusinessUnits

-- Azure resource mappings and metadata
dbo.ResourceTags
dbo.ResourceMappings
dbo.SubscriptionMappings

-- Cost allocation and chargeback rules
dbo.AllocationRules
dbo.ChargebackMappings
dbo.BudgetAllocations

-- Reference data and lookups
dbo.ServiceCategories
dbo.ResourceTypes
dbo.Currencies
dbo.Regions
```

### Features
- **Relational Structure**: Leverages SQL database capabilities for complex joins and relationships
- **Data Integrity**: Enforces referential integrity and business rules
- **Performance**: Optimized for lookup operations and dimensional queries
- **Scalability**: Handles large-scale organizational and resource metadata

## Integration Points

### Data Sources
- **Azure Resource Graph**: Resource metadata and tagging information
- **Active Directory**: Organizational structure and user mappings
- **ERP Systems**: Cost center, department, and budget data
- **ITSM Tools**: Service catalog and ownership information

### Data Consumers  
- **FinOpsHub Lakehouse**: Enriches cost data with dimensional information
- **Power BI Reports**: Provides dimensional context for visualizations
- **Cost Allocation Processes**: Rules engine for automated allocation
- **Governance Dashboards**: Master data quality and completeness metrics

## Deployment Considerations

### Environment Strategy
- **Development**: Full schema with sample/anonymized data
- **Test**: Production-like schema with test data scenarios
- **Production**: Complete master data with proper governance processes

### Data Management
- **Change Control**: Implement approval workflows for master data changes
- **Data Quality**: Regular validation and cleansing processes
- **Backup & Recovery**: Critical for business continuity
- **Access Control**: Role-based access with appropriate permissions

## Security Model

### Recommended Roles
```sql
-- Read-only access for reporting and analytics
db_datareader

-- Write access for data management processes  
db_datawriter

-- Administrative access for schema changes
db_owner

-- Custom roles for specific business functions
MDM_Administrator
MDM_DataSteward  
MDM_Analyst
```

### Row-Level Security
Consider implementing RLS for multi-tenant scenarios or sensitive organizational data.

## Maintenance

### Regular Tasks
- **Data Refresh**: Scheduled updates from authoritative sources
- **Quality Checks**: Automated validation of data completeness and accuracy
- **Performance Monitoring**: Query performance and index optimization
- **Capacity Planning**: Growth monitoring and scaling decisions

### Change Management
- **Schema Evolution**: Version-controlled database changes
- **Data Migration**: Safe migration processes for structural changes
- **Testing**: Comprehensive testing for all master data changes
- **Documentation**: Maintain current documentation of all tables and relationships

## Usage Patterns

### Common Queries
```sql
-- Enrich cost data with organizational context
SELECT c.*, o.DepartmentName, o.CostCenterCode
FROM CostData c
JOIN dbo.ResourceMappings rm ON c.ResourceId = rm.ResourceId  
JOIN dbo.Organizations o ON rm.OrganizationId = o.OrganizationId

-- Cost allocation by business unit
SELECT bu.BusinessUnitName, SUM(c.Cost) as TotalCost
FROM CostData c
JOIN dbo.AllocationRules ar ON c.ServiceName = ar.ServiceName
JOIN dbo.BusinessUnits bu ON ar.BusinessUnitId = bu.BusinessUnitId
GROUP BY bu.BusinessUnitName
```

## Best Practices
1. **Standardization**: Use consistent naming conventions and data formats
2. **Documentation**: Document all tables, columns, and business rules
3. **Validation**: Implement data validation at database and application levels
4. **Audit Trail**: Track changes to master data for compliance and debugging
5. **Performance**: Index frequently queried columns and maintain statistics

## Integration with fabric-cicd
This SQL Database will be deployed automatically through the fabric-cicd pipeline along with other Fabric items, ensuring consistent deployment across environments.