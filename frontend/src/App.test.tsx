import { render, screen } from '@testing-library/react';
import { expect, test } from 'vitest';
import { App } from './App';

test('renders the TCAD Studio connection status', () => {
  render(<App />);

  expect(screen.getByRole('heading', { name: 'TCAD Studio' })).toBeInTheDocument();
  expect(screen.getByRole('status')).toHaveTextContent('正在连接');
});
