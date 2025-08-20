# Fenix Packages

Monorepo for all Fenixflow Python packages.

## Packages

### ff-storage
Database and file storage operations package. Provides PostgreSQL, MySQL connections with pooling support and file storage interfaces for local, S3, and Azure.

**Installation:**
```bash
# From GitLab (production)
pip install git+https://gitlab.com/fenixflow/fenix-packages.git@main#subdirectory=ff-storage

# Local development
pip install -e ./ff-storage
```

## Development

### Building Packages
```bash
# Build all packages
./scripts/build_all.sh

# Build specific package
cd ff-storage && python -m build
```

### Testing
```bash
# Test all packages
./scripts/test_all.sh

# Test specific package
cd ff-storage && pytest tests/
```

### Publishing
Packages are automatically published to GitLab Package Registry on tagged releases.

## Structure
```
fenix-packages/
├── ff-storage/         # Database & file storage
├── ff-tools/          # Future: utility packages
├── ff-auth/           # Future: authentication
└── scripts/           # Build and deployment scripts
```

## Contributing
1. Create feature branch
2. Make changes
3. Add tests
4. Submit merge request

## License
Proprietary - Fenixflow Internal Use Only