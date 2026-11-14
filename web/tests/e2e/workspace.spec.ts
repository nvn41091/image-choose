import { test, expect, type Page } from '@playwright/test';
import { mockSession } from './mocks';
import { blankProject, type Album } from '../../src/model';

const workspace = (): Album => ({
  id: 'studio-one',
  name: 'Minh & An · Bộ ảnh cưới',
  source: 'drive',
  entries: [{ path: 'a.jpg', name: 'a.jpg', id: 'photo123' }],
  project: blankProject(),
  updatedAt: '2026-11-14T00:00:00Z',
  cloudRevision: 1,
  cloudUid: 'test-user',
});
async function seed(page: Page, a = workspace()) {
  await mockSession(page);
  await page.addInitScript((a) => {
    localStorage.setItem('e2e-cloud:test-user', JSON.stringify({ [a.id]: a }));
    localStorage.setItem('e2e-cloud:test-user:active', a.id);
  }, a);
}
const serverPhoto = (page: Page) =>
  page.evaluate(() => {
    const a = JSON.parse(localStorage.getItem('e2e-cloud:test-user') || '{}');
    return a['studio-one']?.project.photos['a.jpg'];
  });

test('requires Google sign-in before displaying any photo tools', async ({ page }) => {
  await mockSession(page);
  await page.goto('/?signedOut=1');
  await expect(
    page.getByRole('button', { name: 'Đăng nhập bằng Google', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.workspace')).toHaveCount(0);
  await expect(page.locator('input[type=file]')).toHaveCount(0);
  await page.waitForFunction(() => Boolean((window as unknown as { google?: unknown }).google));
  await page.getByRole('button', { name: 'Đăng nhập bằng Google', exact: true }).click();
  await expect(page.locator('.welcome')).toBeVisible();
  expect(
    await page.evaluate(
      () => (window as unknown as { testRequestedScopes: string }).testRequestedScopes,
    ),
  ).toContain('openid email profile');
  await expect(
    page.locator('.workspace-identity:visible,.mobile-workspace-identity:visible'),
  ).toContainText('test-user@example.com');
  await page.getByRole('button', { name: 'Đăng xuất Google', exact: true }).click();
  await expect(
    page.getByRole('button', { name: 'Đăng nhập bằng Google', exact: true }),
  ).toBeVisible();
  await expect(page.locator('.workspace')).toHaveCount(0);
});

test('automatically opens the active cloud workspace on a fresh device', async ({ page }, info) => {
  await seed(page);
  await page.goto('/');
  await expect(page.locator('.photo-card')).toHaveCount(1);
  await expect(
    page.locator('.workspace-identity:visible,.mobile-workspace-identity:visible'),
  ).toContainText('Minh & An');
  await expect(page.locator('.gallery-footer')).toContainText('Đã đồng bộ Firebase');
  await page.screenshot({ path: info.outputPath('workspace.png'), fullPage: true });
});

test('autosaves all selection fields and package changes without pressing save', async ({
  page,
  context,
}, info) => {
  await seed(page);
  await page.goto('/');
  await expect(page.locator('.photo-card')).toHaveCount(1);
  await page.getByRole('button', { name: 'Chọn a.jpg', exact: true }).click();
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: 'Loại & ghi chú', exact: true }).click();
  await page.locator('.category-choice').filter({ hasText: 'Album' }).click();
  await page.getByRole('button', { name: 'Đánh giá 4 sao', exact: true }).click();
  await page.getByRole('button', { name: 'Đánh dấu yêu thích', exact: true }).click();
  await page.getByLabel('Điểm ảnh', { exact: true }).fill('88');
  await page.getByLabel('GHI CHÚ HẬU KỲ', { exact: true }).fill('Giữ màu tự nhiên');
  await expect
    .poll(() => serverPhoto(page))
    .toMatchObject({
      category_ids: ['album'],
      stars: 4,
      favorite: true,
      ai_score: 88,
      note: 'Giữ màu tự nhiên',
    });
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: 'Đóng bảng chỉnh ảnh', exact: true }).click();
  await page.getByRole('button', { name: 'Sửa loại ảnh và gói cưới', exact: true }).click();
  await page.getByLabel('Tên khách hàng', { exact: true }).fill('Minh và An');
  await page.getByLabel('Tên loại ảnh', { exact: true }).first().fill('Album chính');
  await page.getByLabel('Tối đa', { exact: true }).first().fill('60');
  await page.getByRole('button', { name: 'Lưu gói ảnh', exact: true }).click();
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          JSON.parse(localStorage.getItem('e2e-cloud:test-user') || '{}')['studio-one']?.project
            .customer_name,
      ),
    )
    .toBe('Minh và An');
  await expect
    .poll(() =>
      page.evaluate(
        () =>
          JSON.parse(localStorage.getItem('e2e-cloud:test-user') || '{}')['studio-one']?.project
            .categories[0],
      ),
    )
    .toMatchObject({ name: 'Album chính', max_count: 60 });
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: 'Loại & ghi chú', exact: true }).click();
  await context.setOffline(true);
  await page.getByLabel('GHI CHÚ HẬU KỲ', { exact: true }).fill('Ghi chú lúc mất mạng');
  await expect(page.locator('.inspector-bottom')).toContainText('chờ kết nối');
  expect((await serverPhoto(page)).note).toBe('Giữ màu tự nhiên');
  await context.setOffline(false);
  await expect
    .poll(() => serverPhoto(page))
    .toMatchObject({ note: 'Ghi chú lúc mất mạng', stars: 4, favorite: true, ai_score: 88 });
  await expect(page.locator('.gallery-footer')).toContainText('Đã đồng bộ Firebase');
});

test('keeps workspaces isolated when a different account signs in', async ({ page }) => {
  await seed(page);
  await page.goto('/');
  await expect(page.locator('.photo-card')).toHaveCount(1);
  await page.goto('/?account=someone-else');
  await expect(page.locator('.welcome')).toBeVisible();
  await expect(page.locator('.photo-card')).toHaveCount(0);
  await expect(
    page.locator('.workspace-identity:visible,.mobile-workspace-identity:visible'),
  ).toContainText('someone-else@example.com');
  await page.goto('/');
  await expect(page.locator('.photo-card')).toHaveCount(1);
});

test('receives other-device edits without discarding an unsent local note', async ({
  page,
}, info) => {
  await seed(page);
  await page.goto('/');
  await page.getByRole('button', { name: 'Chọn a.jpg', exact: true }).click();
  if (info.project.name === 'mobile')
    await page.getByRole('button', { name: 'Loại & ghi chú', exact: true }).click();
  await page.getByLabel('GHI CHÚ HẬU KỲ', { exact: true }).fill('Local note');
  await page.evaluate(() => {
    const key = 'e2e-cloud:test-user',
      albums = JSON.parse(localStorage.getItem(key) || '{}');
    albums['studio-one'].project.photos['a.jpg'] = {
      category_ids: [],
      stars: 5,
      favorite: false,
      ai_score: 99,
      note: '',
      updated_at: new Date().toISOString(),
    };
    albums['studio-one'].cloudRevision = 2;
    localStorage.setItem(key, JSON.stringify(albums));
    window.dispatchEvent(new StorageEvent('storage', { key }));
  });
  await expect
    .poll(() => serverPhoto(page))
    .toMatchObject({ note: 'Local note', stars: 5, ai_score: 99 });
  await expect(page.getByLabel('GHI CHÚ HẬU KỲ', { exact: true })).toHaveValue('Local note');
});
