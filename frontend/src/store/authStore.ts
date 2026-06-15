import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import type { User } from '../types'

interface AuthState {
  user: User | null
  setUser: (user: User) => void
  clearUser: () => void
  isAuthenticated: () => boolean
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      user: null,
      setUser: (user) => set({ user }),
      clearUser: () => set({ user: null }),
      isAuthenticated: () => Boolean(get().user),
    }),
    {
      name: 'finflow-user',
      partialize: (state) => ({ user: state.user }),
    },
  ),
)
