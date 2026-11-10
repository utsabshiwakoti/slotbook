import { Route, Routes } from 'react-router'
import AdminLayout from './pages/admin/AdminLayout'
import Bookings from './pages/admin/Bookings'
import Overview from './pages/admin/Overview'
import Services from './pages/admin/Services'
import Settings from './pages/admin/Settings'
import StaffPage from './pages/admin/Staff'
import TimeOff from './pages/admin/TimeOff'
import BookingPage from './pages/booking/BookingPage'
import ManagePage from './pages/booking/ManagePage'
import Landing from './pages/Landing'
import { Login, Signup } from './pages/AuthPages'
import NotFound from './pages/NotFound'

export default function App() {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/login" element={<Login />} />
      <Route path="/signup" element={<Signup />} />
      <Route path="/b/:slug" element={<BookingPage />} />
      <Route path="/manage/:token" element={<ManagePage />} />
      <Route path="/admin" element={<AdminLayout />}>
        <Route index element={<Overview />} />
        <Route path="bookings" element={<Bookings />} />
        <Route path="services" element={<Services />} />
        <Route path="staff" element={<StaffPage />} />
        <Route path="time-off" element={<TimeOff />} />
        <Route path="settings" element={<Settings />} />
      </Route>
      <Route path="*" element={<NotFound />} />
    </Routes>
  )
}
