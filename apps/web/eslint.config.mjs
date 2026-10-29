import nextVitals from 'eslint-config-next/core-web-vitals';
import {globalIgnores} from 'eslint/config';

const config = [
  ...nextVitals,
  globalIgnores(['.next/**', 'node_modules/**']),
];

export default config;
