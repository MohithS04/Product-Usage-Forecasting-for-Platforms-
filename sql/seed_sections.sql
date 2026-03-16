-- =============================================================================
-- Seed Data: GitLab Platform Sections
-- =============================================================================

INSERT INTO platform_sections (section_name, description, team_owner) VALUES
    ('CI/CD',          'Continuous Integration and Continuous Delivery pipelines', 'Verify Team'),
    ('Container Registry', 'Docker image storage and distribution service',         'Package Team'),
    ('Git Storage',    'Core Git repository hosting and operations',                'Create Team'),
    ('Pages',          'Static site hosting via GitLab Pages',                      'Release Team'),
    ('Runner Fleet',   'Shared and dedicated GitLab runner infrastructure',         'Runner Team'),
    ('Web IDE',        'Browser-based integrated development environment',          'Create Team'),
    ('Monitoring',     'Platform observability and alerting subsystem',             'Ops Team'),
    ('API Gateway',    'REST and GraphQL API layer for external integrations',      'Foundations Team')
ON CONFLICT (section_name) DO NOTHING;
