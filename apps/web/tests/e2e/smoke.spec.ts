import {test,expect} from '@playwright/test';
test('página inicial oferece autenticação',async({page})=>{await page.goto('/');await expect(page.getByText('Entrar')).toBeVisible();});
test('login apresenta campos acessíveis',async({page})=>{await page.goto('/login');await expect(page.getByLabel('E-mail')).toBeVisible();await expect(page.getByLabel('Senha')).toBeVisible();});
